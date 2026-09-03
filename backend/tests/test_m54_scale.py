"""M54 — horizontal scale (docs/research/prod_hardening/PLAN.md M54, spec §18.9).

Where the system stops being one process that happens to run behind a load
balancer: a shared control plane (replica identity and liveness, run
ownership, cancellation as a persisted intent the owner observes, streams
for foreign runs resolving from the record, a persisted job clock, a boot
lock), delivery fan-out over one LISTEN/NOTIFY control channel with a
cluster-wide presence oracle, a declared connection budget, a distributed
rate limiter, generation-guarded cache coherency with TTLs, idempotent MCP
ingest with per-replica reconciliation, and typed per-dimension embedding
columns each with a real HNSW index. Every test runs in one process on the
fake provider; "another replica" is a second replica id acting on the same
database, which is exactly what another process would be.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app import control, replica
from app.db import get_session_factory
from app.llm import fake as fake_llm
from app.models import Conversation, Delivery, McpServer, Run, Tool
from app.orchestrator import admission
from app.orchestrator import runner as runner_mod
from app.settings_store import update_settings

pytestmark = pytest.mark.anyio

API = "/api/v1"
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


@pytest.fixture(autouse=True)
def _own_replica() -> Any:
    replica.set_replica_id("replica-a")
    yield
    replica.set_replica_id(None)


async def _until(pred: Any, timeout_s: float = 10.0, every: float = 0.05) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await pred():
            return
        await asyncio.sleep(every)
    raise AssertionError("condition not reached in time")


async def _run_row(status: str = "running", **kw: Any) -> Run:
    async with get_session_factory()() as session:
        conv = Conversation(title="m54")
        session.add(conv)
        await session.flush()
        run = Run(conversation_id=conv.id, chat_message="m54", status=status, **kw)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def _status(run_id: UUID) -> tuple[str, str | None, datetime | None]:
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        return run.status, run.error, run.cancel_requested_at


async def _heartbeat_as(replica_id: str, *, subscribers: int = 0, age_s: float = 0.0) -> None:
    """Another replica's row, as its own process would write it."""
    now = datetime.now(UTC) - timedelta(seconds=age_s)
    async with get_session_factory()() as session:
        await session.execute(
            text(
                "INSERT INTO replicas (replica_id, started_at, heartbeat_at, subscribers, runs_in_flight) "
                "VALUES (:r, :t, :t, :s, 0) ON CONFLICT (replica_id) DO UPDATE "
                "SET heartbeat_at = EXCLUDED.heartbeat_at, subscribers = EXCLUDED.subscribers"
            ),
            {"r": replica_id, "t": now, "s": subscribers},
        )
        await session.commit()


async def _slow_local_run(monkeypatch: Any, seconds: float = 30.0) -> UUID:
    """A run executing HERE whose body is a long sleep — the shape of a
    provider call in flight — so a cancel has something real to stop."""

    async def slow(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(seconds)

    # stub the graph body, not _execute: its CancelledError handler is the
    # one that finalizes the row (the shape of a real cancel)
    monkeypatch.setattr(runner_mod, "_run_graph", slow)
    run = await runner_mod.create_run(None, "slow one")
    runner_mod.start_run_task(run.id)

    async def running() -> bool:
        return (await _status(run.id))[0] == "running"

    await _until(running)
    return run.id


# ── A. replica identity and liveness ────────────────────────────────


class TestReplicaIdentity:
    def test_identity_is_stable_and_env_overridable(self, monkeypatch: Any) -> None:
        replica.set_replica_id(None)
        monkeypatch.setenv("REPLICA_ID", "blue-1")
        assert replica.replica_id() == "blue-1"
        assert replica.replica_id() == "blue-1"
        replica.set_replica_id(None)
        monkeypatch.delenv("REPLICA_ID")
        first = replica.replica_id()
        assert first and first == replica.replica_id()

    async def test_heartbeat_row_and_liveness(self) -> None:
        await replica.heartbeat_once(subscribers=3, runs_in_flight=1)
        await _heartbeat_as("replica-b", subscribers=2)
        await _heartbeat_as("replica-dead", subscribers=9, age_s=replica.REPLICA_DEAD_AFTER_S + 5)
        live = await replica.live_replica_ids()
        assert {"replica-a", "replica-b"} <= live
        assert "replica-dead" not in live
        # the cluster audience: this replica's live count plus the fresh
        # counts of the OTHER live replicas — never the dead one's, never
        # this replica's own stale row
        assert await replica.cluster_audience(local=1) == 3

    async def test_replicas_endpoint_lists_the_fleet_and_the_budget(
        self, client: AsyncClient
    ) -> None:
        await replica.heartbeat_once(subscribers=0, runs_in_flight=0)
        await _heartbeat_as("replica-b", subscribers=1)
        resp = await client.get(f"{API}/replicas")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["self"] == "replica-a"
        ids = {r["replica_id"] for r in body["replicas"]}
        assert {"replica-a", "replica-b"} <= ids
        assert all("live" in r and "heartbeat_at" in r for r in body["replicas"])
        budget = body["budget"]
        for key in ("per_replica", "replicas", "declared_max", "needed", "fits"):
            assert key in budget, key

    async def test_retire_removes_the_row(self) -> None:
        await replica.heartbeat_once()
        await replica.retire()
        assert "replica-a" not in await replica.live_replica_ids()


# ── B. run ownership, cancellation as intent, foreign streams ────────


class TestRunOwnership:
    async def test_created_run_is_owned_by_this_replica(self) -> None:
        run = await runner_mod.create_run(None, "who owns me")
        assert run.owner_replica == "replica-a"

    async def test_local_cancel_still_cancels_the_task(self, monkeypatch: Any) -> None:
        run_id = await _slow_local_run(monkeypatch)
        assert await runner_mod.cancel_run(run_id) == "cancelled"
        status, error, _ = await _status(run_id)
        assert status == "cancelled"
        assert run_id not in runner_mod.RUNNING_TASKS

    async def test_foreign_cancel_is_an_intent_not_a_lie(self, monkeypatch: Any) -> None:
        """A run executing on another replica: this replica must not write
        `cancelled` (the old false-cancel that resurrected as completed).
        It records the intent, announces it, and reports the truth."""
        announced: list[dict[str, Any]] = []

        async def capture(kind: str, **fields: Any) -> None:
            announced.append({"kind": kind, **fields})

        monkeypatch.setattr(control, "notify", capture)
        monkeypatch.setattr(runner_mod, "CANCEL_WAIT_S", 0.3)
        run = await _run_row("running", owner_replica="replica-b")
        outcome = await runner_mod.cancel_run(run.id)
        assert outcome == "cancel_requested"
        status, _, requested = await _status(run.id)
        assert status == "running" and requested is not None
        assert announced and announced[0]["kind"] == "cancel"
        assert announced[0]["run_id"] == str(run.id)

    async def test_foreign_cancel_reports_cancelled_once_the_owner_acts(
        self, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(runner_mod, "CANCEL_WAIT_S", 2.0)
        run = await _run_row("running", owner_replica="replica-b")

        async def owner_acts() -> None:
            await asyncio.sleep(0.2)
            async with get_session_factory()() as session:
                row = await session.get(Run, run.id)
                assert row is not None
                row.status = "cancelled"
                await session.commit()

        task = asyncio.create_task(owner_acts())
        assert await runner_mod.cancel_run(run.id) == "cancelled"
        await task

    async def test_cancel_api_reports_the_real_status(
        self, client: AsyncClient, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(runner_mod, "CANCEL_WAIT_S", 0.2)
        run = await _run_row("running", owner_replica="replica-b")
        resp = await client.post(f"{API}/runs/{run.id}/cancel")
        assert resp.status_code == 202, resp.text
        assert resp.json()["status"] == "cancel_requested"

    async def test_owner_observes_the_intent_from_the_control_channel(
        self, monkeypatch: Any
    ) -> None:
        run_id = await _slow_local_run(monkeypatch)
        async with get_session_factory()() as session:
            await session.execute(
                text("UPDATE runs SET cancel_requested_at = now() WHERE id = :id"), {"id": run_id}
            )
            await session.commit()
        control.dispatch(
            json.dumps({"kind": "cancel", "run_id": str(run_id), "origin": "replica-b"})
        )

        async def cancelled() -> bool:
            return (await _status(run_id))[0] == "cancelled"

        await _until(cancelled, timeout_s=5)
        _, error, _ = await _status(run_id)
        assert error and "cancelled by request" in error

    async def test_owner_observes_the_intent_from_its_heartbeat(self, monkeypatch: Any) -> None:
        """A lost NOTIFY still cancels: the heartbeat re-reads the intent."""
        monkeypatch.setattr(runner_mod, "HEARTBEAT_INTERVAL_S", 0.2)
        run_id = await _slow_local_run(monkeypatch)
        async with get_session_factory()() as session:
            await session.execute(
                text("UPDATE runs SET cancel_requested_at = now() WHERE id = :id"), {"id": run_id}
            )
            await session.commit()

        async def cancelled() -> bool:
            return (await _status(run_id))[0] == "cancelled"

        await _until(cancelled, timeout_s=5)

    async def test_boot_reap_is_scoped_to_this_replica(self) -> None:
        await _heartbeat_as("replica-b")
        mine = await _run_row("running", owner_replica="replica-a")
        legacy = await _run_row("queued", owner_replica=None)
        theirs = await _run_row("running", owner_replica="replica-b")
        reaped = await runner_mod.reap_orphaned_runs()
        assert reaped == 2
        assert (await _status(mine.id))[0] == "failed"
        assert (await _status(legacy.id))[0] == "failed"
        assert (await _status(theirs.id))[0] == "running", (
            "another replica's run is not ours to fail"
        )

    async def test_dead_owner_runs_are_reaped_truthfully(self) -> None:
        await _heartbeat_as("replica-b")
        await _heartbeat_as("replica-gone", age_s=replica.REPLICA_DEAD_AFTER_S + 5)
        alive = await _run_row("running", owner_replica="replica-b")
        orphan = await _run_row("running", owner_replica="replica-gone")
        queued_orphan = await _run_row("queued", owner_replica="replica-gone")
        unknown = await _run_row("running", owner_replica="never-seen")
        assert await runner_mod.reap_dead_owner_runs() == 3
        assert (await _status(alive.id))[0] == "running"
        for row in (orphan, queued_orphan, unknown):
            status, error, _ = await _status(row.id)
            assert status == "failed" and error and "owner replica gone" in error

    async def test_terminal_transitions_are_announced(
        self, client: AsyncClient, monkeypatch: Any
    ) -> None:
        announced: list[dict[str, Any]] = []

        async def capture(kind: str, **fields: Any) -> None:
            announced.append({"kind": kind, **fields})

        monkeypatch.setattr(control, "notify", capture)
        fake_llm.push_ai(
            "",
            tool_calls=[
                {
                    "name": "PlannerOutput",
                    "args": {"entries": [], "direct_answer": "Lisbon", "no_confident_match": False},
                    "id": "p1",
                }
            ],
        )
        resp = await client.post(f"{API}/chat", json={"message": "capital of Portugal?"})
        run_id = resp.json()["run_id"]

        async def done() -> bool:
            return (await _status(UUID(run_id)))[0] == "completed"

        await _until(done)
        terminal = [a for a in announced if a["kind"] == "terminal"]
        assert terminal and terminal[-1]["run_id"] == run_id
        assert terminal[-1]["status"] == "completed"

    async def test_foreign_stream_resolves_when_the_owner_announces(self) -> None:
        from app.api.chat import stream_run_events

        run = await _run_row("running", owner_replica="replica-b")
        gen = stream_run_events(run.id, after=3)
        got: list[dict[str, Any]] = []

        async def consume() -> None:
            async for event in gen:
                got.append(event)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.3)
        assert not got, "nothing to serve yet: the run is executing elsewhere"
        async with get_session_factory()() as session:
            row = await session.get(Run, run.id)
            assert row is not None
            row.status = "completed"
            row.final_answer = "from the record"
            await session.commit()
        control.dispatch(
            json.dumps(
                {
                    "kind": "terminal",
                    "run_id": str(run.id),
                    "status": "completed",
                    "origin": "replica-b",
                }
            )
        )
        await asyncio.wait_for(task, timeout=5)
        kinds = [e["event"] for e in got]
        assert kinds == ["run_status", "done"]
        assert [e["id"] for e in got] == ["4", "5"]
        assert json.loads(got[1]["data"])["payload"]["answer"] == "from the record"

    async def test_foreign_stream_falls_back_to_the_row_at_each_beat(
        self, monkeypatch: Any
    ) -> None:
        from app.api import chat

        monkeypatch.setattr(chat, "SSE_HEARTBEAT_S", 0.2)
        run = await _run_row("running", owner_replica="replica-b")
        gen = chat.stream_run_events(run.id)
        got: list[dict[str, Any]] = []

        async def consume() -> None:
            async for event in gen:
                got.append(event)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.5)
        assert {e["event"] for e in got} <= {"ping"}
        async with get_session_factory()() as session:
            row = await session.get(Run, run.id)
            assert row is not None
            row.status = "cancelled"
            await session.commit()
        await asyncio.wait_for(task, timeout=5)
        assert got[-1]["event"] == "run_status"
        assert json.loads(got[-1]["data"])["payload"]["status"] == "cancelled"


# ── C. the persisted job clock and the boot lock ─────────────────────


class TestJobClock:
    async def test_due_then_ran_then_not_due_until_the_interval(self) -> None:
        from app.jobclock import job_due, job_ran, last_run

        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        assert await job_due("probe", 3600, now=t0)
        await job_ran("probe", now=t0)
        assert (await last_run("probe")) == t0
        assert not await job_due("probe", 3600, now=t0 + timedelta(minutes=59))
        assert await job_due("probe", 3600, now=t0 + timedelta(minutes=61))

    async def test_consolidation_runs_once_per_interval_across_processes(
        self, monkeypatch: Any
    ) -> None:
        """Two ticks — as two replicas would tick — run a due job once; a
        'restart' (the per-process state gone) does not run it again."""
        from app.memory import lifecycle

        await _set(memory_enabled=True, memory_decay_enabled=True)
        calls: list[int] = []

        async def counted() -> int:
            calls.append(1)
            return 0

        monkeypatch.setattr(lifecycle, "decay_sweep", counted)
        await lifecycle.run_due_jobs()
        # a second tick — another replica's, or this one's after a restart:
        # nothing process-local decides whether the job is due
        await lifecycle.run_due_jobs()
        assert len(calls) == 1, "the clock lives in the database, not the process"
        assert "job_due(" in inspect.getsource(lifecycle._due)
        assert "job_ran(" in inspect.getsource(lifecycle.run_due_jobs)

    async def test_retention_keeps_the_same_clock(self) -> None:
        from app import retention

        src = inspect.getsource(retention.maybe_run_retention)
        assert "job_due(" in src and "job_ran(" in src
        assert await retention.maybe_run_retention() is not None
        assert await retention.maybe_run_retention() is None

    async def test_boot_lock_is_a_session_advisory_lock(self) -> None:
        from app.replica import BOOT_LOCK_CLASSID, boot_lock

        async with boot_lock(), get_session_factory()() as session:
            held = await session.scalar(
                text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=:c"),
                {"c": BOOT_LOCK_CLASSID},
            )
            assert held == 1
            other = await session.scalar(
                text("SELECT pg_try_advisory_lock(:c, 1)"), {"c": BOOT_LOCK_CLASSID}
            )
            assert other is False, "a second booter waits"
        async with get_session_factory()() as session:
            held = await session.scalar(
                text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=:c"),
                {"c": BOOT_LOCK_CLASSID},
            )
            assert held == 0

    def test_lifespan_boots_under_the_lock(self) -> None:
        from app import main

        src = inspect.getsource(main.lifespan)
        assert "boot_lock()" in src
        assert src.index("boot_lock()") < src.index("_run_migrations")


# ── D. delivery fan-out and the cluster audience ─────────────────────


def _delivery(**kw: Any) -> Delivery:
    return Delivery(
        id=kw.get("id", uuid4()),
        tier=kw.get("tier", 1),
        urgency=kw.get("urgency", 3),
        category=kw.get("category", "m54"),
        title=kw.get("title", "m54 toast"),
        body=kw.get("body", ""),
        created_at=datetime.now(UTC),
    )


class TestDeliveryFanOut:
    async def test_publish_announces_and_fan_in_reaches_local_subscribers(
        self, monkeypatch: Any
    ) -> None:
        from app.ambient import channels

        announced: list[dict[str, Any]] = []

        async def capture(kind: str, **fields: Any) -> None:
            announced.append({"kind": kind, "origin": replica.replica_id(), **fields})

        monkeypatch.setattr(control, "notify", capture)
        sub_id, queue = channels.subscribe_stream()
        try:
            await channels.publish("notify", [_delivery(title="hello fleet")])
            assert announced and announced[0]["kind"] == "delivery"
            assert announced[0]["origin"] == "replica-a"
            local = queue.get_nowait()
            assert local["title"] == "hello fleet"
            # the same payload arriving from ANOTHER replica fans in here
            foreign = dict(announced[0])
            foreign["origin"] = "replica-b"
            control.dispatch(json.dumps(foreign))
            again = queue.get_nowait()
            assert again["title"] == "hello fleet" and again["seq"] > local["seq"]
            # our own announcement coming back is ignored — no double toast
            control.dispatch(json.dumps(announced[0]))
            assert queue.empty()
        finally:
            channels.unsubscribe_stream(sub_id)

    async def test_pursuit_uses_the_cluster_audience(self, monkeypatch: Any) -> None:
        """Nobody subscribed HERE, two people on another replica: the toast
        reached them, so the in-app outcome is not 'unseen' and pursuit
        'away' holds the external channel."""
        from app.ambient import channels

        async def quiet(kind: str, **fields: Any) -> None:
            return None

        monkeypatch.setattr(control, "notify", quiet)
        await _heartbeat_as("replica-b", subscribers=2)
        sent: list[str] = []

        async def fake_webhook(mode: str, rows: list[Delivery]) -> None:
            sent.append(mode)

        channels.register_channel_adapter("webhook", fake_webhook)
        try:
            await _set(
                ambient_enabled=True,
                ambient_pursuit="away",
                ambient_channels={"notify": ["in_app", "webhook"]},
            )
            entries = await channels.dispatch_delivered("notify", [_delivery()], record=False)
        finally:
            channels.register_channel_adapter("webhook", None)
        assert "in_app" not in entries, "the toast reached two people on replica-b"
        assert sent == [], "pursuit 'away' holds the external channel"


# ── E. the connection budget ─────────────────────────────────────────


class TestConnectionBudget:
    def test_arithmetic_is_published(self, monkeypatch: Any) -> None:
        from app import db
        from app.config import get_config

        get_config.cache_clear()
        monkeypatch.setenv("DB_POOL_SIZE", "5")
        monkeypatch.setenv("DB_MAX_OVERFLOW", "10")
        monkeypatch.setenv("DB_REPLICAS", "3")
        monkeypatch.setenv("DB_MAX_CONNECTIONS", "100")
        try:
            budget = db.connection_budget()
            assert budget["per_replica"] == 5 + 10 + db.CHECKPOINTER_POOL + db.SESSION_CONNECTIONS
            assert budget["replicas"] == 3 and budget["declared_max"] == 100
            assert budget["needed"] == 3 * budget["per_replica"] + db.RESERVED_CONNECTIONS
            assert budget["fits"] is (budget["needed"] <= 100)
            monkeypatch.setenv("DB_MAX_CONNECTIONS", "40")
            get_config.cache_clear()
            assert db.connection_budget()["fits"] is False
        finally:
            get_config.cache_clear()

    def test_pooled_connections_survive_a_transaction_pooler(self) -> None:
        from app import db
        from app.config import get_config

        assert get_config().db_statement_cache_size == 0
        args = db.engine_connect_args()
        assert args["statement_cache_size"] == 0
        assert args["prepared_statement_cache_size"] == 0
        src = inspect.getsource(db.get_engine)
        assert "engine_connect_args()" in src


# ── F. the distributed rate limiter ──────────────────────────────────


class TestDistributedRateLimiter:
    async def test_one_bucket_for_every_replica(self) -> None:
        from app import ratelimit

        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        key = f"user:{uuid4()}"
        assert await ratelimit.allow(key, burst=2, per_s=1.0, now=t0)
        assert await ratelimit.allow(key, burst=2, per_s=1.0, now=t0)
        assert not await ratelimit.allow(key, burst=2, per_s=1.0, now=t0)
        # refill is time, in the database — any replica sees the same bucket
        assert await ratelimit.allow(key, burst=2, per_s=1.0, now=t0 + timedelta(seconds=1))
        assert not await ratelimit.allow(key, burst=2, per_s=1.0, now=t0 + timedelta(seconds=1))

    async def test_idle_keys_are_evicted(self) -> None:
        from app import ratelimit

        t0 = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        await ratelimit.allow("ip:1.2.3.4", burst=5, per_s=1.0, now=t0)
        await ratelimit.allow("ip:5.6.7.8", burst=5, per_s=1.0, now=t0 + timedelta(hours=2))
        assert await ratelimit.evict_idle(idle_s=3600, now=t0 + timedelta(hours=2)) == 1
        async with get_session_factory()() as session:
            left = await session.scalar(text("SELECT count(*) FROM rate_buckets"))
        assert left == 1

    def test_middleware_uses_the_shared_bucket_and_the_loop_evicts(self) -> None:
        from app import auth
        from app.memory import lifecycle

        assert "ratelimit.allow" in inspect.getsource(auth.AuthMiddleware.dispatch)
        assert "evict_idle" in inspect.getsource(lifecycle.run_periodic_loop)


# ── G. cache coherency ───────────────────────────────────────────────


class TestCacheCoherency:
    async def test_a_dirty_mark_during_a_reload_is_not_lost(self, monkeypatch: Any) -> None:
        from app import registry_cache
        from app.registry_cache import get_cache

        cache = get_cache()
        real_load = registry_cache._load_registry
        marked = asyncio.Event()

        async def slow_load(registry: str) -> Any:
            data = await real_load(registry)
            if registry == "tools" and not marked.is_set():
                marked.set()
                await cache._mark_dirty("tools")  # a peer's NOTIFY lands mid-load
            return data

        monkeypatch.setattr(registry_cache, "_load_registry", slow_load)
        await cache.set_mode("memory")  # the warm load is the load the mark lands in
        assert "tools" in cache._dirty, "the generation moved under the load: still dirty"
        status = await cache.status()
        assert status["registries"]["tools"]["dirty"] is True
        # the next read honours the mark: one more load, then clean
        await cache._ensure("tools")
        assert "tools" not in cache._dirty
        assert marked.is_set()

    async def test_memory_entries_expire_on_the_ttl(self, monkeypatch: Any) -> None:
        from app import registry_cache
        from app.registry_cache import get_cache

        cache = get_cache()
        calls: list[str] = []
        real_load = registry_cache._load_registry

        async def counted(registry: str) -> Any:
            calls.append(registry)
            return await real_load(registry)

        monkeypatch.setattr(registry_cache, "_load_registry", counted)
        monkeypatch.setattr(registry_cache, "CACHE_TTL_S", 0.1)
        await cache.set_mode("memory")  # the warm load is the first load
        await cache._ensure("skills")
        await cache._ensure("skills")
        assert calls.count("skills") == 1
        await asyncio.sleep(0.15)
        await cache._ensure("skills")
        assert calls.count("skills") == 2, "past the TTL the entry is reloaded"

    def test_redis_blob_is_written_with_a_ttl_and_under_the_generation_guard(self) -> None:
        from app import registry_cache

        src = inspect.getsource(registry_cache.RegistryCache._ensure)
        assert "ex=" in src or "setex" in src
        assert "generation" in src


# ── H. MCP under N replicas ──────────────────────────────────────────


async def _stub_server(name: str) -> UUID:
    async with get_session_factory()() as session:
        server = McpServer(
            name=name, transport="stdio", command=sys.executable, args=[STUB], source="dynamic"
        )
        session.add(server)
        await session.commit()
        return server.id


class TestMcpUnderReplicas:
    async def test_concurrent_ingest_is_idempotent(self) -> None:
        from app.mcp.manager import McpManager

        manager = McpManager()
        server_id = await _stub_server("m54-stub")
        try:
            await manager.connect_server(server_id)
            await asyncio.gather(*(manager._ingest(server_id) for _ in range(4)))
            async with get_session_factory()() as session:
                rows = list(
                    (
                        await session.execute(select(Tool).where(Tool.mcp_server_id == server_id))
                    ).scalars()
                )
            names = sorted(r.tool_name for r in rows)
            assert len(names) == len(set(names)), "one row per tool, whoever ingested"
            assert "echo" in names
            src = inspect.getsource(manager._ingest)
            assert "on_conflict" in src and "advisory" in src
        finally:
            await manager.stop()

    async def test_each_replica_reconciles_its_subprocess_set(self) -> None:
        from app.mcp.manager import McpManager

        manager = McpManager()
        try:
            server_id = await _stub_server("m54-elsewhere")  # registered on another replica
            assert not manager.is_connected(server_id)
            await manager.reconcile()
            assert manager.is_connected(server_id)
            async with get_session_factory()() as session:
                row = await session.get(McpServer, server_id)
                assert row is not None
                row.deleted_at = datetime.now(UTC)  # deleted on another replica
                await session.commit()
            await manager.reconcile()
            assert not manager.is_connected(server_id)
            assert "reconcile" in inspect.getsource(manager._health_loop)
        finally:
            await manager.stop()


# ── I. typed per-dimension embeddings ────────────────────────────────


class TestTypedEmbeddings:
    def test_column_routing(self) -> None:
        from app.memory.dims import EMBEDDING_DIMS, dims_of, embedding_column

        assert 64 in EMBEDDING_DIMS and 1536 in EMBEDDING_DIMS and 3072 in EMBEDDING_DIMS
        assert embedding_column(64) == "emb_64"
        assert embedding_column(1536) == "emb_1536"
        assert embedding_column(77) is None
        assert dims_of("fake:scripted@64") == 64
        assert dims_of("openai:text-embedding-3-large@3072") == 3072
        assert dims_of("nodims") is None

    async def test_write_lands_in_the_typed_column_with_an_hnsw_index(
        self, client: AsyncClient
    ) -> None:
        await _set(memory_enabled=True, embedding_model="fake:scripted")
        resp = await client.post(
            f"{API}/memories", json={"text": "the fleet has three replicas", "kind": "fact"}
        )
        assert resp.status_code == 201, resp.text
        async with get_session_factory()() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT model_key, emb_64 IS NOT NULL AS typed FROM memory_embeddings "
                        "WHERE table_ref = 'memories'"
                    )
                )
            ).first()
            assert row is not None and row.model_key == "fake:scripted@64" and row.typed
            index = await session.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE tablename = 'memory_embeddings' "
                    "AND indexname = 'memory_embeddings_emb_64_hnsw'"
                )
            )
            assert index and "hnsw" in index and "vector_cosine_ops" in index
            columns = {
                r[0]
                for r in (
                    await session.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'memory_embeddings'"
                        )
                    )
                ).all()
            }
            assert "embedding" not in columns, "the untyped column is gone"
            assert {"emb_64", "emb_768", "emb_1536", "emb_3072"} <= columns
        recall = await client.get(f"{API}/memories/recall", params={"q": "three replicas"})
        assert recall.status_code == 200, recall.text
        assert any("three replicas" in r["memory"]["text"] for r in recall.json())

    def test_every_vector_query_uses_the_typed_column(self) -> None:
        from app.memory import episodic, procedural, rank

        for module in (rank, procedural, episodic):
            src = inspect.getsource(module)
            assert "e.embedding <=>" not in src and "emb.embedding <=>" not in src, module.__name__
            assert "embedding_column(" in src or "vector_column(" in src, module.__name__
