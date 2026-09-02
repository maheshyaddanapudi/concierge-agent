"""M53 — deploy and operate (docs/research/prod_hardening/PLAN.md M53).

The wave where the system becomes something an operator can deploy, watch
and trim: an SSE wire format that survives a reconnect (ids, Last-Event-ID,
a heartbeat inside the tightest balancer default), a readiness-first drain
with a polite stream close, a leader lease released by awaiting the loop,
retention for the six unbounded tables — each behind its own §3.7.1 gate —
saturation and error signals on /metrics carrying the §10 labels, MCP
reconnection with a circuit breaker and re-ingest that keeps operator
intent, supervised LISTEN connections, and a cost model with a shared spend
ceiling across every trigger kind. These tests pin each of those.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from prometheus_client import generate_latest
from sqlalchemy import select, text

from app import obs
from app.db import get_session_factory
from app.llm import fake as fake_llm
from app.models import (
    A2ATask,
    AmbientEvent,
    AmbientPolicy,
    AuthSession,
    Conversation,
    Delivery,
    McpServer,
    PatternInstance,
    RemoteAgent,
    Routine,
    Run,
    RunStep,
    Tool,
    User,
)
from app.orchestrator import admission
from app.orchestrator.context import RunEventBus
from app.settings_store import DEFAULTS, update_settings

pytestmark = pytest.mark.anyio

API = "/api/v1"
REPO = Path(__file__).resolve().parents[2]
STUB = str(Path(__file__).resolve().parent / "stub_mcp_server.py")


async def _set(**kv: Any) -> None:
    async with get_session_factory()() as session:
        await update_settings(session, kv)


@pytest.fixture(autouse=True)
def _fresh_admission() -> Any:
    admission.reset()
    yield
    admission.reset()


@pytest.fixture(autouse=True)
async def _fake_model(_database: None) -> None:
    async with get_session_factory()() as session:
        await update_settings(
            session,
            {
                "default_model": "fake:scripted",
                "formatter_enabled": False,
                "orchestrator_mode": "graph",
            },
        )


def plan_call(direct_answer: str) -> None:
    fake_llm.push_ai(
        "",
        tool_calls=[
            {
                "name": "PlannerOutput",
                "args": {
                    "entries": [],
                    "direct_answer": direct_answer,
                    "no_confident_match": False,
                },
                "id": f"p{uuid4().hex[:6]}",
            }
        ],
    )


async def send_chat(client: AsyncClient, message: str = "do the thing") -> str:
    resp = await client.post(f"{API}/chat", json={"message": message})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["run_id"])


async def wait_run(
    client: AsyncClient, run_id: str, statuses: set[str], timeout_s: float = 20.0
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout_s
    run: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        run = (await client.get(f"{API}/runs/{run_id}")).json()
        if run["status"] in statuses:
            return dict(run)
        await asyncio.sleep(0.1)
    raise AssertionError(f"run did not reach {statuses}; last: {run.get('status')}")


async def _run_row(status: str = "completed", **kw: Any) -> Run:
    async with get_session_factory()() as session:
        conv = Conversation(title="m53")
        session.add(conv)
        await session.flush()
        run = Run(conversation_id=conv.id, chat_message="m53", status=status, **kw)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


def _parse_sse(body: str) -> list[dict[str, str]]:
    """Wire → records: one dict per blank-line-terminated event."""
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if line.startswith(":"):
            current.setdefault("comment", line[1:].strip())
            continue
        field, _, value = line.partition(":")
        current[field.strip()] = value.strip()
    if current:
        records.append(current)
    return records


async def _stream(client: AsyncClient, path: str, **headers: str) -> list[dict[str, str]]:
    async with client.stream("GET", path, headers=headers) as resp:
        assert resp.status_code == 200, await resp.aread()
        body = (await resp.aread()).decode()
    return _parse_sse(body)


async def _collect(gen: AsyncIterator[dict[str, Any]], n: int, timeout_s: float = 3.0) -> list[Any]:
    out: list[Any] = []
    try:
        async with asyncio.timeout(timeout_s):
            async for item in gen:
                out.append(item)
                if len(out) >= n:
                    break
    finally:
        await gen.aclose()
    return out


# ── A. SSE wire format (scale-B3) ────────────────────────────────────


class TestSseWireFormat:
    def test_bus_assigns_monotonic_seq_and_resumes_after(self) -> None:
        bus = RunEventBus()
        rid = uuid4()
        for i in range(3):
            bus.emit(rid, {"type": "token", "payload": {"text": str(i)}})
        history, _ = bus.subscribe(rid)
        assert [e["seq"] for e in history] == [1, 2, 3]
        assert bus.last_seq(rid) == 3
        resumed, _ = bus.subscribe(rid, after=2)
        assert [e["seq"] for e in resumed] == [3]
        # a subscriber that is already caught up gets nothing replayed
        assert bus.subscribe(rid, after=3)[0] == []

    async def test_stream_carries_ids_and_last_event_id_resumes(self, client: AsyncClient) -> None:
        plan_call(direct_answer="resumable answer")
        run_id = await send_chat(client, "stream me")
        await wait_run(client, run_id, {"completed"})
        records = [r for r in await _stream(client, f"{API}/chat/stream/{run_id}") if "event" in r]
        ids = [int(r["id"]) for r in records if r.get("id")]
        assert ids and ids == sorted(ids) and len(set(ids)) == len(ids), ids
        assert all("id" in r for r in records), "every run event carries an id"
        assert records[-1]["event"] == "done"
        token_text = "".join(
            json.loads(r["data"])["payload"]["text"] for r in records if r["event"] == "token"
        )
        assert "resumable answer" in token_text
        # reconnect from the middle: only the tail is replayed, so no token
        # text is ever delivered twice to a client that kept its Last-Event-ID
        cut = ids[len(ids) // 2]
        tail = [
            r
            for r in await _stream(
                client, f"{API}/chat/stream/{run_id}", **{"Last-Event-ID": str(cut)}
            )
            if "event" in r
        ]
        assert [int(r["id"]) for r in tail] == [i for i in ids if i > cut]
        assert tail[-1]["event"] == "done"
        # the query form serves clients that cannot set the header
        via_query = [
            r
            for r in await _stream(client, f"{API}/chat/stream/{run_id}?after={ids[-2]}")
            if "event" in r
        ]
        assert [int(r["id"]) for r in via_query] == [ids[-1]]

    async def test_terminal_events_are_synthesized_when_history_is_gone(
        self, client: AsyncClient
    ) -> None:
        """After a deploy the new process has no bus history; a reconnecting
        client (Last-Event-ID in hand) still resolves from the run row."""
        done = await _run_row("completed", final_answer="the durable answer")
        records = [
            r
            for r in await _stream(client, f"{API}/chat/stream/{done.id}", **{"Last-Event-ID": "7"})
            if "event" in r
        ]
        assert [r["event"] for r in records] == ["run_status", "done"]
        assert [int(r["id"]) for r in records] == [8, 9]  # continues the client's sequence
        assert json.loads(records[-1]["data"])["payload"]["answer"] == "the durable answer"
        failed = await _run_row("failed", error="provider went away")
        records = [
            r for r in await _stream(client, f"{API}/chat/stream/{failed.id}") if "event" in r
        ]
        assert [r["event"] for r in records] == ["error", "run_status"]
        assert json.loads(records[0]["data"])["payload"]["message"] == "provider went away"
        assert json.loads(records[1]["data"])["payload"]["status"] == "failed"
        cancelled = await _run_row("cancelled", error="cancelled by shutdown")
        records = [
            r for r in await _stream(client, f"{API}/chat/stream/{cancelled.id}") if "event" in r
        ]
        assert [r["event"] for r in records] == ["run_status"]

    async def test_heartbeat_is_inside_the_tightest_balancer_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.api import chat

        assert chat.SSE_HEARTBEAT_S <= 15
        monkeypatch.setattr(chat, "SSE_HEARTBEAT_S", 0.1)
        running = await _run_row("running")
        events = await _collect(chat.stream_run_events(running.id, after=0), 2)
        assert [e["event"] for e in events] == ["ping", "ping"]
        assert all("id" not in e for e in events), "heartbeats never advance the sequence"

    async def test_draining_process_closes_streams_it_cannot_serve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.api import chat
        from app.orchestrator.runner import RUNNING_TASKS

        monkeypatch.setattr(chat, "SSE_HEARTBEAT_S", 0.1)
        paused = await _run_row("paused_hitl")
        admission.begin_drain()
        events = await _collect(chat.stream_run_events(paused.id, after=3), 3)
        # the paused status is synthesized from the row (id 4), then the
        # polite close — a paused run makes no progress in a draining process
        assert [e["event"] for e in events] == ["run_status", "reconnect"], events
        assert events[0]["id"] == "4"
        hint = events[1]
        assert int(hint["retry"]) >= 1000
        assert json.loads(hint["data"])["reason"] == "draining"
        # a run THIS process is executing keeps streaming until it ends
        owned = await _run_row("running")
        RUNNING_TASKS[owned.id] = asyncio.create_task(asyncio.sleep(5))
        try:
            events = await _collect(chat.stream_run_events(owned.id, after=0), 2)
            assert [e["event"] for e in events] == ["ping", "ping"]
        finally:
            RUNNING_TASKS.pop(owned.id).cancel()

    async def test_ambient_stream_carries_ids_and_heartbeats(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ambient import channels
        from app.api import ambient as ambient_api

        await _set(ambient_enabled=True)
        monkeypatch.setattr(channels, "STREAM_KEEPALIVE_S", 0.1)
        try:
            gen = ambient_api.ambient_event_stream()
            first = await _collect(gen, 1)
            assert first[0]["event"] == "ping"
            gen = ambient_api.ambient_event_stream()
            task = asyncio.create_task(_collect(gen, 2))
            await asyncio.sleep(0.05)
            row = Delivery(title="toast", tier=0, urgency=5, category="ops")
            channels._publish("interrupt", [row])
            got = await task
            delivered = [e for e in got if e["event"] == "delivery"]
            assert delivered and delivered[0]["id"].isdigit()
            assert json.loads(delivered[0]["data"])["title"] == "toast"
        finally:
            await _set(ambient_enabled=False)

    async def test_sse_subscriber_gauge_tracks_open_streams(self) -> None:
        from app.orchestrator.context import EVENT_BUS

        rid = uuid4()
        before = obs.SSE_SUBSCRIBERS.labels(stream="chat")._value.get()
        _, queue = EVENT_BUS.subscribe(rid)
        assert obs.SSE_SUBSCRIBERS.labels(stream="chat")._value.get() == before + 1
        EVENT_BUS.unsubscribe(rid, queue)
        assert obs.SSE_SUBSCRIBERS.labels(stream="chat")._value.get() == before


# ── B. deploy lifecycle (scale-H1) ───────────────────────────────────


class TestDeployLifecycle:
    async def test_begin_drain_flips_readiness_first_and_refuses_runs(
        self, client: AsyncClient
    ) -> None:
        ready = await client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready" and ready.json()["db"] == "ok"
        admission.begin_drain()
        assert admission.draining_since() is not None
        ready = await client.get("/ready")
        assert ready.status_code == 503 and ready.json()["status"] == "draining"
        # liveness is unaffected — a draining process is alive, just not routable
        assert (await client.get("/health")).status_code == 200
        shed = await client.post(f"{API}/chat", json={"message": "late"})
        assert shed.status_code == 503 and "Retry-After" in shed.headers

    async def test_sigusr1_begins_the_drain(self) -> None:
        """The pre-stop hook: a signal flips readiness while the listener is
        still open, so a balancer sees the 503 BEFORE SIGTERM closes the port."""
        loop = asyncio.get_running_loop()
        assert admission.install_drain_signal() is True
        try:
            assert admission.accepting()
            os.kill(os.getpid(), signal.SIGUSR1)
            for _ in range(50):
                if not admission.accepting():
                    break
                await asyncio.sleep(0.02)
            assert not admission.accepting(), "SIGUSR1 must start the drain"
        finally:
            loop.remove_signal_handler(signal.SIGUSR1)

    async def test_ready_reports_the_database_and_degrades_without_it(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import main

        async def broken() -> None:
            raise RuntimeError("connection refused")

        monkeypatch.setattr(main, "_db_probe", broken)
        ready = await client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "degraded"
        assert ready.json()["db"].startswith("error")
        assert (await client.get("/health")).status_code == 200  # liveness never probes the DB

    async def test_ambient_loop_releases_the_lease_when_cancelled_and_awaited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ambient import drain as drain_mod
        from app.ambient.coordinate import LeaderLease

        async def no_op() -> None:
            return None

        async def no_drain() -> int:
            return 0

        monkeypatch.setattr("app.ambient.triggers.evaluate_schedules", no_op)
        monkeypatch.setattr(drain_mod, "drain_once", no_drain)
        await _set(ambient_enabled=True)
        stop = asyncio.Event()
        task = asyncio.create_task(drain_mod.run_ambient_loop(stop, tick_s=0.1))
        probe = LeaderLease()
        try:
            for _ in range(40):
                await asyncio.sleep(0.05)
                if not await probe.ensure():
                    break
                await probe.release()
            assert not probe.held, "the loop never took the lease"
            # the shutdown path: cancel and AWAIT — the lease must be gone
            # the moment the await returns, not when a dead session lapses
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
            assert await probe.ensure() is True, "lease not released by the cancelled loop"
        finally:
            await probe.release()
            stop.set()
            await _set(ambient_enabled=False)

    def test_shutdown_awaits_the_loops_it_cancels(self) -> None:
        src = (REPO / "backend" / "app" / "main.py").read_text()
        assert "await _settle(ambient_loop_task" in src
        assert "await _settle(memory_loop_task" in src
        assert "install_drain_signal" in src

    def test_deploy_artifacts(self) -> None:
        import yaml

        dockerfile = (REPO / "backend" / "Dockerfile").read_text()
        assert "--timeout-graceful-shutdown" in dockerfile
        compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
        backend = compose["services"]["backend"]
        assert "healthcheck" in backend and backend["healthcheck"]["test"]
        assert backend["restart"] == "unless-stopped"
        assert backend["deploy"]["resources"]["limits"]["memory"]
        grace = int(str(backend["stop_grace_period"]).rstrip("s"))
        assert grace >= 35, "the drain (25 s) plus uvicorn's connection grace must fit"
        for name in ("db", "frontend"):
            assert compose["services"][name]["restart"] == "unless-stopped"
        assert compose["services"]["frontend"]["depends_on"]["backend"]["condition"] == (
            "service_healthy"
        )
        nginx = (REPO / "frontend" / "nginx.conf").read_text()
        assert "http2" in nginx
        deploy = REPO / "deploy.sh"
        assert deploy.exists() and os.access(deploy, os.X_OK)
        assert "USR1" in deploy.read_text()
        assert (REPO / "backup.sh").exists() and (REPO / "restore.sh").exists()


# ── C. retention (arch-M6) ───────────────────────────────────────────


OLD = datetime.now(UTC) - timedelta(days=400)


async def _seed_retention_rows() -> dict[str, dict[str, UUID]]:
    """Per table: one row retention must delete, one it must never touch."""
    ids: dict[str, dict[str, UUID]] = {}
    async with get_session_factory()() as session:
        user = User(username=f"u-{uuid4().hex[:6]}", password_hash="x")
        agent = RemoteAgent(name=f"agent-{uuid4().hex[:6]}", card_url="https://example.test/card")
        session.add_all([user, agent])
        await session.flush()
        rows: dict[str, dict[str, Any]] = {
            "ambient_events": {
                "gone": AmbientEvent(kind="k", source="user", verdict="held"),
                "kept": AmbientEvent(kind="k", source="user", verdict=None),  # pending
            },
            "deliveries": {
                "gone": Delivery(title="old", delivered_at=OLD),
                "kept": Delivery(title="pending"),  # never delivered
            },
            "ambient_policies": {
                "gone": AmbientPolicy(category="ops", reason="older"),
                "kept": AmbientPolicy(category="ops", reason="latest"),  # latest per category
            },
            "pattern_instances": {
                "gone": PatternInstance(rule_key="r", partition_key="a", state="matched"),
                "kept": PatternInstance(rule_key="r", partition_key="b", state="armed"),
            },
            "a2a_tasks": {
                "gone": A2ATask(remote_agent_id=agent.id, state="completed"),
                "kept": A2ATask(remote_agent_id=agent.id, state="parked"),
            },
            "auth_sessions": {
                "gone": AuthSession(user_id=user.id, token_hash=uuid4().hex, expires_at=OLD),
                "kept": AuthSession(
                    user_id=user.id,
                    token_hash=uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                ),
            },
        }
        for pair in rows.values():
            session.add_all(pair.values())
        await session.commit()
        for table, pair in rows.items():
            ids[table] = {k: v.id for k, v in pair.items()}
        # age everything: the timestamp columns are server defaults
        for table in ("ambient_events",):
            await session.execute(
                text(f"UPDATE {table} SET received_at = :old, occurred_at = :old"),  # noqa: S608 - fixed names
                {"old": OLD},
            )
        for table in ("deliveries", "ambient_policies", "pattern_instances", "auth_sessions"):
            await session.execute(
                text(f"UPDATE {table} SET created_at = :old"),  # noqa: S608 - fixed names
                {"old": OLD},
            )
        # the latest policy row must stay the latest even when aged
        await session.execute(
            text("UPDATE ambient_policies SET created_at = :newer WHERE id = :id"),
            {"newer": OLD + timedelta(days=1), "id": ids["ambient_policies"]["kept"]},
        )
        await session.execute(
            text("UPDATE a2a_tasks SET created_at = :old, updated_at = :old"), {"old": OLD}
        )
        await session.commit()
    return ids


async def _present(table: str, row_id: UUID) -> bool:
    async with get_session_factory()() as session:
        got = await session.execute(
            text(f"SELECT 1 FROM {table} WHERE id = :id"),  # noqa: S608 - fixed names
            {"id": row_id},
        )
        return got.first() is not None


class TestRetention:
    def test_every_unbounded_table_has_its_own_gate_and_window(self) -> None:
        from app.retention import RETENTION_GATES, RETENTION_TABLES, RETENTION_WINDOWS

        assert set(RETENTION_TABLES) == {
            "ambient_events",
            "deliveries",
            "ambient_policies",
            "pattern_instances",
            "a2a_tasks",
            "auth_sessions",
        }
        for table in RETENTION_TABLES:
            gate, window = RETENTION_GATES[table], RETENTION_WINDOWS[table]
            assert gate in DEFAULTS and window in DEFAULTS, table
            assert isinstance(DEFAULTS[gate], bool)
            assert isinstance(DEFAULTS[window], int) and DEFAULTS[window] >= 1

    def test_destructive_jobs_are_born_dark_except_expired_sessions(self) -> None:
        from app.retention import RETENTION_GATES

        for table, gate in RETENTION_GATES.items():
            expected = table == "auth_sessions"  # expired-only, mirrors the login-time sweep
            assert DEFAULTS[gate] is expected, f"{gate} default"

    @pytest.mark.parametrize(
        "table",
        [
            "ambient_events",
            "deliveries",
            "ambient_policies",
            "pattern_instances",
            "a2a_tasks",
            "auth_sessions",
        ],
    )
    async def test_gate_holds_on_direct_calls_and_protected_rows_survive(
        self, client: AsyncClient, table: str
    ) -> None:
        from app.retention import RETENTION_GATES, RETENTION_WINDOWS, purge_table

        ids = await _seed_retention_rows()
        await _set(**{RETENTION_GATES[table]: False, RETENTION_WINDOWS[table]: 30})
        try:
            assert await purge_table(table) == 0
            assert await _present(table, ids[table]["gone"])
            await _set(**{RETENTION_GATES[table]: True})
            assert await purge_table(table) == 1
            assert not await _present(table, ids[table]["gone"])
            assert await _present(table, ids[table]["kept"]), f"{table}: protected row deleted"
            assert await purge_table(table) == 0  # idempotent
        finally:
            await _set(
                **{
                    RETENTION_GATES[table]: DEFAULTS[RETENTION_GATES[table]],
                    RETENTION_WINDOWS[table]: DEFAULTS[RETENTION_WINDOWS[table]],
                }
            )

    async def test_window_keeps_young_rows(self, client: AsyncClient) -> None:
        from app.retention import purge_table

        ids = await _seed_retention_rows()
        await _set(retention_deliveries_enabled=True, retention_deliveries_days=3650)
        try:
            assert await purge_table("deliveries") == 0
            assert await _present("deliveries", ids["deliveries"]["gone"])
        finally:
            await _set(retention_deliveries_enabled=False, retention_deliveries_days=90)

    async def test_windows_validate(self, client: AsyncClient) -> None:
        bad = await client.patch(f"{API}/settings", json={"retention_deliveries_days": 0})
        assert bad.status_code == 422 and "retention_deliveries_days" in bad.text
        bad = await client.patch(f"{API}/settings", json={"retention_deliveries_days": 99999})
        assert bad.status_code == 422
        ok = await client.patch(f"{API}/settings", json={"retention_deliveries_days": 45})
        assert ok.status_code == 200 and ok.json()["retention_deliveries_days"] == 45
        await _set(retention_deliveries_days=90)

    async def test_run_and_preview_surfaces(self, client: AsyncClient) -> None:
        from app.retention import RETENTION_TABLES

        ids = await _seed_retention_rows()
        await _set(retention_pattern_instances_enabled=True, retention_pattern_instances_days=1)
        try:
            preview = (await client.get(f"{API}/retention")).json()
            by_table = {row["table"]: row for row in preview["tables"]}
            assert set(by_table) == set(RETENTION_TABLES)
            assert by_table["pattern_instances"]["enabled"] is True
            assert by_table["pattern_instances"]["eligible"] == 1
            assert by_table["deliveries"]["enabled"] is False
            assert by_table["deliveries"]["eligible"] == 1  # counted even while dark
            ran = (await client.post(f"{API}/retention/run")).json()
            assert ran["deleted"]["pattern_instances"] == 1
            assert ran["deleted"]["deliveries"] == 0  # gate held inside the job
            assert not await _present("pattern_instances", ids["pattern_instances"]["gone"])
        finally:
            await _set(
                retention_pattern_instances_enabled=False, retention_pattern_instances_days=7
            )

    async def test_retention_runs_under_an_advisory_lock(self) -> None:
        from app.retention import RETENTION_LOCK_CLASSID, RETENTION_LOCK_OBJID, run_retention

        assert RETENTION_LOCK_CLASSID not in (42016, 427017)  # never collides with memory/leader
        async with get_session_factory()() as session:
            held = (
                await session.execute(
                    text("SELECT pg_try_advisory_lock(:c, :o)"),
                    {"c": RETENTION_LOCK_CLASSID, "o": RETENTION_LOCK_OBJID},
                )
            ).scalar()
            assert held is True
            try:
                assert await run_retention() == {}  # another replica holds it: skip, no error
            finally:
                await session.execute(
                    text("SELECT pg_advisory_unlock(:c, :o)"),
                    {"c": RETENTION_LOCK_CLASSID, "o": RETENTION_LOCK_OBJID},
                )
        result = await run_retention()
        assert set(result) == {
            "ambient_events",
            "deliveries",
            "ambient_policies",
            "pattern_instances",
            "a2a_tasks",
            "auth_sessions",
        }

    def test_retention_ticks_from_the_periodic_loop(self) -> None:
        src = (REPO / "backend" / "app" / "memory" / "lifecycle.py").read_text()
        assert "run_retention" in src, "the periodic loop must tick retention"


# ── D. observability (arch-M7) ───────────────────────────────────────


def _counter(metric: Any, **labels: str) -> float:
    return float(metric.labels(**labels)._value.get())


class TestObservability:
    async def test_llm_calls_are_measured_at_the_port(self) -> None:
        from app.llm import get_model

        model = get_model("fake:scripted")
        ok_before = _counter(obs.LLM_CALLS, provider="fake", model="scripted", status="ok")
        fake_llm.push_ai("measured")
        out = await model.ainvoke("hello")
        assert out.content == "measured"
        assert (
            _counter(obs.LLM_CALLS, provider="fake", model="scripted", status="ok") == ok_before + 1
        )
        rl_before = _counter(
            obs.LLM_CALLS, provider="fake", model="scripted", status="rate_limited"
        )
        fake_llm.push_error(RuntimeError("429 rate limit exceeded"))
        with pytest.raises(RuntimeError):
            await model.ainvoke("again")
        assert (
            _counter(obs.LLM_CALLS, provider="fake", model="scripted", status="rate_limited")
            == rl_before + 1
        )
        text_out = generate_latest().decode()
        assert (
            'concierge_llm_latency_seconds_count{model="scripted",provider="fake",status="ok"}'
            in text_out
        )

    async def test_step_metrics_carry_the_section_10_labels(self) -> None:
        from app.orchestrator.recorder import RunRecorder

        run = await _run_row("running")
        recorder = RunRecorder(run.id)
        step = await recorder.start_step(
            "skill",
            tier="skill",
            kind="native",
            source="static",
            model="fake:scripted",
            effort="low",
        )
        await recorder.finish_step(step, input_tokens=3, output_tokens=4)
        body = generate_latest().decode()
        assert (
            'concierge_steps_total{effort="low",kind="native",model="fake:scripted",'
            'source="static",status="completed",tier="skill"}'
        ) in body
        assert (
            'concierge_step_duration_seconds_count{effort="low",kind="native",model="fake:scripted"'
            in body
        )

    async def test_saturation_gauges_are_exported(self, client: AsyncClient) -> None:
        body = (await client.get("/metrics")).text
        for series in (
            'concierge_db_pool_connections{state="checked_out"}',
            'concierge_db_pool_connections{state="capacity"}',
            "concierge_db_pool_saturation",
            'concierge_runs_in_flight{state="running"}',
            'concierge_runs_in_flight{state="queued"}',
            "concierge_run_slots",
        ):
            assert series in body, series
        assert obs.LOOP_ERRORS._labelnames == ("loop",)
        assert obs.BACKLOG._labelnames == ("queue",)
        assert obs.MCP_SERVERS._labelnames == ("state",)
        assert obs.LISTENER_CONNECTED._labelnames == ("channel",)

    async def test_in_flight_gauge_follows_admission(self) -> None:
        rid = uuid4()
        async with admission.slot(rid, {"run_max_concurrent": 2, "run_queue_max": 1}):
            assert obs.RUNS_IN_FLIGHT.labels(state="running")._value.get() == 1
            assert obs.RUN_SLOTS._value.get() == 2
        assert obs.RUNS_IN_FLIGHT.labels(state="running")._value.get() == 0

    async def test_backlog_gauges_reflect_pending_rows(self) -> None:
        from app.ambient.drain import record_backlog_depth

        async with get_session_factory()() as session:
            session.add_all(
                [
                    AmbientEvent(kind="k", source="user"),
                    AmbientEvent(kind="k", source="user"),
                    AmbientEvent(kind="k", source="user", verdict="held"),
                    Delivery(title="pending"),
                    Delivery(title="done", delivered_at=datetime.now(UTC)),
                ]
            )
            await session.commit()
        depth = await record_backlog_depth()
        assert depth == {"ambient_events": 2, "deliveries": 1}
        assert obs.BACKLOG.labels(queue="ambient_events")._value.get() == 2
        assert obs.BACKLOG.labels(queue="deliveries")._value.get() == 1

    async def test_loop_errors_are_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.memory import lifecycle

        async def boom() -> dict[str, int]:
            raise RuntimeError("tick exploded")

        monkeypatch.setattr(lifecycle, "run_due_jobs", boom)
        before = _counter(obs.LOOP_ERRORS, loop="memory")
        stop = asyncio.Event()
        task = asyncio.create_task(lifecycle.run_periodic_loop(stop, tick_s=0.05))
        await asyncio.sleep(0.2)
        stop.set()
        await task
        assert _counter(obs.LOOP_ERRORS, loop="memory") > before


# ── E. MCP reconnection + re-ingest intent ───────────────────────────


async def _make_stub(extra_args: list[str] | None = None, **overrides: Any) -> UUID:
    async with get_session_factory()() as session:
        fields: dict[str, Any] = {
            "name": overrides.pop("name", f"stub-{uuid4().hex[:6]}"),
            "description": "stub server",
            "transport": "stdio",
            "command": sys.executable,
            "args": [STUB, *(extra_args or [])],
            "source": "dynamic",
            "status": "inactive",
        }
        fields.update(overrides)
        server = McpServer(**fields)
        session.add(server)
        await session.commit()
        return server.id


async def _server(server_id: UUID) -> McpServer:
    async with get_session_factory()() as session:
        row = await session.get(McpServer, server_id)
        if row is None:
            raise AssertionError("server vanished")
        return row


async def _tools_of(server_id: UUID) -> dict[str, Tool]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(select(Tool).where(Tool.mcp_server_id == server_id))
        ).scalars()
        return {t.tool_name: t for t in rows}


async def _until(predicate: Any, timeout_s: float = 15.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not met within timeout")


@pytest.fixture
async def manager(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    from app.mcp.manager import McpManager, set_manager

    monkeypatch.setattr(McpManager, "RECONNECT_BASE_S", 0.05)
    monkeypatch.setattr(McpManager, "RECONNECT_CAP_S", 0.2)
    m = McpManager()
    set_manager(m)
    yield m
    set_manager(None)
    await m.stop()


class TestMcpReconnect:
    async def test_failed_ping_reconnects_with_backoff(self, manager: Any) -> None:
        server_id = await _make_stub()
        await manager.connect_server(server_id)
        assert (await _server(server_id)).status == "active"
        ok_before = _counter(obs.MCP_RECONNECTS, outcome="ok")
        tools = await manager.get_langchain_tools(server_id, ["die"])
        with contextlib.suppress(Exception):
            await asyncio.wait_for(tools[0].ainvoke({}), timeout=5)
        await manager.ping_all()
        assert (await _server(server_id)).status == "error"
        state = manager.reconnect_state(server_id)
        assert state["scheduled"] is True and state["circuit_open"] is False

        async def back() -> bool:
            return (await _server(server_id)).status == "active"

        await _until(back)
        assert manager.reconnect_state(server_id)["attempts"] == 0  # success resets the budget
        assert _counter(obs.MCP_RECONNECTS, outcome="ok") == ok_before + 1

    async def test_circuit_opens_after_the_attempt_budget(self, manager: Any) -> None:
        await _set(mcp_reconnect_max_attempts=2)
        try:
            server_id = await _make_stub(extra_args=["--fail"])
            await manager.connect_server(server_id)
            assert (await _server(server_id)).status == "error"

            async def opened() -> bool:
                return manager.reconnect_state(server_id)["circuit_open"]

            await _until(opened)
            state = manager.reconnect_state(server_id)
            assert state["attempts"] == 2 and state["scheduled"] is False
            row = await _server(server_id)
            assert row.status == "error" and "circuit open" in (row.last_error or "")
            await asyncio.sleep(0.5)
            assert manager.reconnect_state(server_id)["attempts"] == 2, "breaker must hold"
            assert obs.MCP_SERVERS.labels(state="circuit_open")._value.get() >= 1
            # an operator's explicit reconnect resets the breaker
            await manager.connect_server(server_id)
            assert manager.reconnect_state(server_id)["circuit_open"] is False
        finally:
            await _set(mcp_reconnect_max_attempts=8)

    async def test_auto_reconnect_gate_off_means_no_attempts(self, manager: Any) -> None:
        await _set(mcp_auto_reconnect_enabled=False)
        try:
            server_id = await _make_stub(extra_args=["--fail"])
            await manager.connect_server(server_id)
            await asyncio.sleep(0.5)
            state = manager.reconnect_state(server_id)
            assert state["attempts"] == 0 and state["scheduled"] is False
        finally:
            await _set(mcp_auto_reconnect_enabled=True)

    async def test_reingest_preserves_operator_intent(
        self, manager: Any, client: AsyncClient
    ) -> None:
        server_id = await _make_stub()
        await manager.connect_server(server_id)
        tools = await _tools_of(server_id)
        assert tools["echo"].ingest_state == "present"
        # the operator disables a tool the server still offers
        off = await client.patch(f"{API}/tools/{tools['echo'].id}", json={"status": "inactive"})
        assert off.status_code == 200
        await manager.refresh_tools(server_id)
        assert (await _tools_of(server_id))["echo"].status == "inactive", "re-ingest resurrected it"
        # the server drops a tool: inactive, and marked as the server's doing
        mutate = await manager.get_langchain_tools(server_id, ["mutate_toolset"])
        await mutate[0].ainvoke({})

        async def dropped() -> bool:
            t = await _tools_of(server_id)
            return t["add"].status == "inactive" and t["add"].ingest_state == "missing"

        await _until(dropped)
        # a fresh process offers `add` again: the SERVER's inactivity ends,
        # the OPERATOR's does not
        await manager.connect_server(server_id)
        tools = await _tools_of(server_id)
        assert tools["add"].status == "active" and tools["add"].ingest_state == "present"
        assert tools["echo"].status == "inactive"
        # a soft-deleted tool stays deleted across re-ingest, and restore brings it back
        deleted = await client.delete(f"{API}/tools/{tools['echo'].id}")
        assert deleted.status_code == 204
        await manager.refresh_tools(server_id)
        assert (await _tools_of(server_id))["echo"].deleted_at is not None
        restored = await client.post(f"{API}/tools/{tools['echo'].id}/restore")
        assert restored.status_code == 200 and restored.json()["deleted_at"] is None


# ── F. supervised LISTEN ─────────────────────────────────────────────


async def _terminate_backend(pid: int) -> None:
    async with get_session_factory()() as session:
        await session.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        await session.commit()


class TestSupervisedListen:
    async def test_listener_reconnects_after_its_backend_dies(self) -> None:
        from app.listen import SupervisedListener

        heard: list[str] = []
        reconnects: list[int] = []
        listener = SupervisedListener(
            "m53_probe",
            lambda payload: heard.append(payload),
            on_reconnect=lambda: reconnects.append(1),
            base_backoff_s=0.05,
            max_backoff_s=0.2,
            heartbeat_s=0.5,
        )
        await listener.start()
        try:
            assert listener.connected
            assert obs.LISTENER_CONNECTED.labels(channel="m53_probe")._value.get() == 1
            before = _counter(obs.LISTENER_RECONNECTS, channel="m53_probe")
            pid = listener.server_pid()
            assert pid
            # the session is findable by name — how an operator (or the
            # §14p-88 drill) tells the listeners from the pool
            async with get_session_factory()() as session:
                name = await session.scalar(
                    text("SELECT application_name FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            assert name == "concierge-listen:m53_probe"
            await _terminate_backend(pid)

            async def back_up() -> bool:
                return listener.connected and listener.server_pid() not in (None, pid)

            await _until(back_up, timeout_s=10)
            assert reconnects, "on_reconnect must fire so callers can reload missed state"
            assert _counter(obs.LISTENER_RECONNECTS, channel="m53_probe") == before + 1
            async with get_session_factory()() as session:
                await session.execute(text("SELECT pg_notify('m53_probe', 'after-reconnect')"))
                await session.commit()

            async def delivered() -> bool:
                return "after-reconnect" in heard

            await _until(delivered, timeout_s=5)
        finally:
            await listener.stop()
        assert not listener.connected
        assert obs.LISTENER_CONNECTED.labels(channel="m53_probe")._value.get() == 0

    async def test_registry_cache_reloads_after_a_listener_gap(self) -> None:
        from app.registry_cache import REGISTRIES, get_cache

        cache = get_cache()
        await cache.set_mode("memory")
        await cache.start_listener(base_backoff_s=0.05)
        try:
            assert cache.listener_connected
            for registry in REGISTRIES:
                await cache._ensure(registry)
            assert cache._dirty == set()
            pid = cache.listener_pid()
            assert pid
            await _terminate_backend(pid)

            async def dirty_again() -> bool:
                return cache.listener_connected and cache._dirty == set(REGISTRIES)

            await _until(dirty_again, timeout_s=10)
        finally:
            await cache.stop_listener()


# ── G. cost model + spend ceiling ────────────────────────────────────


class TestCostModel:
    def test_price_table_and_cost_math(self) -> None:
        from app.llm import pricing

        assert pricing.price_for("anthropic:claude-sonnet-4-6") is not None
        assert pricing.price_for("nobody:nothing") is None
        per_in, per_out = pricing.price_for("anthropic:claude-sonnet-4-6") or (0.0, 0.0)
        assert pricing.cost_usd("anthropic:claude-sonnet-4-6", 1_000_000, 0) == pytest.approx(
            per_in
        )
        assert pricing.cost_usd("anthropic:claude-sonnet-4-6", 0, 1_000_000) == pytest.approx(
            per_out
        )
        assert pricing.cost_usd("nobody:nothing", 10, 10) is None
        overrides = {"nobody:nothing": {"input_per_m": 2.0, "output_per_m": 4.0}}
        assert pricing.cost_usd("nobody:nothing", 500_000, 250_000, overrides) == pytest.approx(2.0)
        assert pricing.cost_usd("fake:scripted", 1_000_000, 0) == 0.0  # free by definition
        for ref in pricing.DEFAULT_PRICES:
            assert ":" in ref

    async def test_run_cost_is_computed_from_captured_usage(self, client: AsyncClient) -> None:
        run = await _run_row("completed", total_input_tokens=1_500_000, total_output_tokens=0)
        async with get_session_factory()() as session:
            session.add_all(
                [
                    RunStep(
                        run_id=run.id,
                        step_type="skill",
                        model="anobody:alpha",
                        input_tokens=1_000_000,
                        status="completed",
                    ),
                    RunStep(
                        run_id=run.id,
                        step_type="aggregate",
                        model="anobody:beta",
                        input_tokens=250_000,
                        status="completed",
                    ),
                ]
            )
            await session.commit()
        await _set(
            model_prices={
                "anobody:alpha": {"input_per_m": 1.0, "output_per_m": 1.0},
                "anobody:beta": {"input_per_m": 4.0, "output_per_m": 4.0},
                "fake:scripted": {"input_per_m": 8.0, "output_per_m": 8.0},
            },
            default_model="fake:scripted",
        )
        try:
            out = (await client.get(f"{API}/runs/{run.id}")).json()
            # 1.0 (alpha) + 1.0 (beta) + the 250k un-stepped remainder at the default model (2.0)
            assert out["cost_usd"] == pytest.approx(4.0)
            assert out["cost_priced"] is True
            listed = (await client.get(f"{API}/runs")).json()
            assert any(
                r["id"] == str(run.id) and r["cost_usd"] == pytest.approx(4.0) for r in listed
            )
            await _set(model_prices={})
            out = (await client.get(f"{API}/runs/{run.id}")).json()
            assert out["cost_priced"] is False  # unknown models are reported, never guessed
        finally:
            await _set(model_prices={}, default_model="fake:scripted")

    async def test_model_prices_validate(self, client: AsyncClient) -> None:
        bad = await client.patch(
            f"{API}/settings", json={"model_prices": {"x": {"input_per_m": -1}}}
        )
        assert bad.status_code == 422
        bad = await client.patch(f"{API}/settings", json={"model_prices": {"noprovider": {}}})
        assert bad.status_code == 422
        bad = await client.patch(f"{API}/settings", json={"spend_ceiling_usd_per_day": 0})
        assert bad.status_code == 422

    async def test_spend_ceiling_refuses_every_trigger_kind(self, client: AsyncClient) -> None:
        from app.cost import SpendCeilingReached, invalidate_spend_cache
        from app.orchestrator.runner import create_run

        spent = await _run_row("completed", total_input_tokens=1_000_000)
        assert spent.id
        await _set(
            model_prices={"fake:scripted": {"input_per_m": 5.0, "output_per_m": 5.0}},
            default_model="fake:scripted",
            spend_ceiling_enabled=True,
            spend_ceiling_usd_per_day=1.0,
        )
        invalidate_spend_cache()
        try:
            spend = (await client.get(f"{API}/spend")).json()
            assert spend["usd_today"] == pytest.approx(5.0)
            assert spend["ceiling"]["enabled"] is True and spend["ceiling"]["reached"] is True
            refused = await client.post(f"{API}/chat", json={"message": "one more"})
            assert refused.status_code == 429, refused.text
            assert "spend ceiling" in refused.json()["detail"]
            assert "Retry-After" in refused.headers
            with pytest.raises(SpendCeilingReached):
                await create_run(None, "eval case", is_eval=True)
            # an ambient fire is HELD with the reason on the event, never a crash
            from app.ambient.execute import execute_fired_event
            from app.ambient.store import emit_event

            await _set(ambient_enabled=True)
            async with get_session_factory()() as session:
                routine = Routine(name=f"r-{uuid4().hex[:6]}", prompt="check")
                session.add(routine)
                await session.commit()
                routine_id = routine.id
            event = await emit_event(
                kind="routine_schedule", source="schedule", payload=None, routine_id=routine_id
            )
            assert event is not None
            async with get_session_factory()() as session:
                row = await session.get(AmbientEvent, event.id)
                assert row is not None
                row.verdict = "fired"
                row.decision = {"tier": 1, "urgency": 2, "fired_for": "routine"}
                await session.commit()
            assert await execute_fired_event(event.id, poll_s=0.1) is None
            async with get_session_factory()() as session:
                row = await session.get(AmbientEvent, event.id)
                assert row is not None
                assert row.verdict == "held" and "spend ceiling" in (row.verdict_reason or "")
            assert _counter(obs.SPEND_REFUSED, kind="ambient") >= 1
            # gate off ⇒ byte-identical admission
            await _set(spend_ceiling_enabled=False)
            invalidate_spend_cache()
            plan_call(direct_answer="allowed again")
            assert (await client.post(f"{API}/chat", json={"message": "ok"})).status_code == 201
        finally:
            await _set(
                spend_ceiling_enabled=False,
                spend_ceiling_usd_per_day=10.0,
                model_prices={},
                ambient_enabled=False,
            )
            invalidate_spend_cache()

    async def test_spend_gauge_is_published_by_the_periodic_tick(self) -> None:
        """A fresh process must not report $0 for a day that cost money:
        the periodic loop publishes the gauge whether or not the ceiling
        gate is on (the load drill caught the dashboard saying $0)."""
        import inspect

        from app.cost import invalidate_spend_cache, refresh_spend_gauge
        from app.memory import lifecycle

        await _run_row("completed", total_input_tokens=1_000_000)
        await _set(model_prices={"fake:scripted": {"input_per_m": 1.0, "output_per_m": 1.0}})
        invalidate_spend_cache()
        obs.SPEND_TODAY.set(0.0)
        try:
            await refresh_spend_gauge()
            assert obs.SPEND_TODAY._value.get() >= 1.0
            src = inspect.getsource(lifecycle.run_periodic_loop)
            assert "refresh_spend_gauge" in src, "the periodic loop must publish the spend gauge"
        finally:
            await _set(model_prices={})
            invalidate_spend_cache()

    async def test_spend_endpoint_breaks_down_by_kind(self, client: AsyncClient) -> None:
        from app.cost import invalidate_spend_cache

        await _run_row("completed", total_input_tokens=1_000_000)
        await _run_row("completed", total_input_tokens=1_000_000, is_eval=True)
        await _run_row(
            "completed", total_input_tokens=1_000_000, trigger={"routine_id": str(uuid4())}
        )
        await _set(model_prices={"fake:scripted": {"input_per_m": 1.0, "output_per_m": 1.0}})
        invalidate_spend_cache()
        try:
            spend = (await client.get(f"{API}/spend")).json()
            assert spend["by_kind"] == {
                "chat": pytest.approx(1.0),
                "eval": pytest.approx(1.0),
                "ambient": pytest.approx(1.0),
            }
            assert spend["usd_today"] == pytest.approx(3.0)
            assert spend["runs_today"] == 3
            assert spend["ceiling"]["enabled"] is False
        finally:
            await _set(model_prices={})
            invalidate_spend_cache()
