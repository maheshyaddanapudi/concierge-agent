"""M51 — bounded work (docs/research/prod_hardening/PLAN.md M51).

Every unit of work gets a ceiling and a truthful end state: provider calls
carry a timeout and a retry budget set at the port, every run has a wall
clock and a heartbeat, admission is bounded with an explicit shed-load
response, the event bus is bounded, shutdown drains and restart reaps,
sessions never span a provider call, deliveries retry with backoff and
dead-letter, token totals increment atomically, and the contradiction
sweep keeps the newest fact. These tests pin each of those.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app import db as app_db
from app import obs
from app.config import AppConfig, get_config
from app.db import get_session_factory
from app.llm import fake as fake_llm
from app.llm import get_provider, list_providers, validate_model_selection
from app.llm.port import ModelInfo, classify_provider_error
from app.models import AmbientEvent, Conversation, Delivery, Memory, Run, RunStep
from app.settings_store import update_settings

pytestmark = pytest.mark.anyio

API = "/api/v1"


async def _set(**kv: Any) -> None:
    async with get_session_factory()() as session:
        await update_settings(session, kv)


async def _run_row(status: str = "running", **kw: Any) -> Run:
    async with get_session_factory()() as session:
        conv = Conversation(title="m51")
        session.add(conv)
        await session.flush()
        run = Run(conversation_id=conv.id, chat_message="m51", status=status, **kw)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def _status(run_id: UUID) -> tuple[str, str | None]:
    async with get_session_factory()() as session:
        row = await session.get(Run, run_id)
        if row is None:
            raise AssertionError("run vanished")
        return row.status, row.error


# ── A. limits at the provider port ──────────────────────────────────


def test_port_limits_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLM_TIMEOUT_S", "LLM_MAX_RETRIES"):
        monkeypatch.setenv(var, "")
    cfg = AppConfig(_env_file=None)
    assert (cfg.llm_timeout_s, cfg.llm_max_retries) == (120, 2)
    monkeypatch.setenv("LLM_TIMEOUT_S", "45")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    cfg = AppConfig(_env_file=None)
    assert (cfg.llm_timeout_s, cfg.llm_max_retries) == (45, 0)


_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@pytest.mark.parametrize(
    "provider", list_providers(), ids=[p.provider_id for p in list_providers()]
)
def test_every_adapter_honors_the_port_limits(
    provider: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract: the timeout and retry budget are set ONCE, at the port —
    every adapter's model carries them (the port is unbreached, so this is
    the one place a hang or a retry storm can be bounded)."""
    monkeypatch.setenv("LLM_TIMEOUT_S", "33")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    if provider.provider_id in _KEY_ENV:
        monkeypatch.setenv(_KEY_ENV[provider.provider_id], "test-key")
    elif provider.provider_id == "custom":
        monkeypatch.setenv("CUSTOM_GATEWAY_BASE_URL", "https://gateway.test/v1")
        monkeypatch.setenv("CUSTOM_GATEWAY_API_KEY", "test-key")
        monkeypatch.setenv("CUSTOM_GATEWAY_MODELS", "gw-model")
    elif provider.provider_id == "fake":
        monkeypatch.setenv("FAKE_LLM_ENABLED", "1")
    get_config.cache_clear()
    try:
        model = provider.get_chat_model(provider.list_models()[0].id)
        timeout = next(
            (
                getattr(model, attr)
                for attr in ("timeout", "request_timeout", "default_request_timeout")
                if getattr(model, attr, None) is not None
            ),
            None,
        )
        assert timeout == 33, f"{provider.provider_id}: timeout not applied ({timeout!r})"
        assert getattr(model, "max_retries", None) == 1, f"{provider.provider_id}: max_retries"
    finally:
        get_config.cache_clear()


def test_provider_errors_are_classified() -> None:
    class RateLimitError(Exception):
        status_code = 429

    class NotFoundError(Exception):
        status_code = 404

    assert classify_provider_error(RateLimitError("slow down")) == "rate_limited"
    assert classify_provider_error(TimeoutError()) == "timeout"
    assert classify_provider_error(NotFoundError("model x does not exist")) == "unknown_model"
    assert classify_provider_error(RuntimeError("model 'y' has been deprecated")) == "unknown_model"
    assert classify_provider_error(RuntimeError("boom")) == "provider_error"


def test_retired_model_is_refused_at_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A retired model reference fails loudly at settings-validation time."""
    fake = get_provider("fake")
    real = fake.list_models

    def with_retired() -> list[ModelInfo]:
        return [*real(), ModelInfo("scripted-old", "Scripted (retired)", deprecated=True)]

    monkeypatch.setattr(type(fake), "list_models", staticmethod(with_retired))
    errors = validate_model_selection("fake:scripted-old")
    assert errors and "retired" in errors[0]
    assert validate_model_selection("fake:scripted") == []


async def test_provider_failure_names_the_setting_it_came_from(client: AsyncClient) -> None:
    """At call time the failure says WHICH model, WHY (classified), and which
    setting resolved it — not an opaque provider traceback."""
    await _set(default_model="fake:scripted", formatter_enabled=False, orchestrator_mode="graph")

    class RateLimitError(Exception):
        status_code = 429

    fake_llm.push_error(RateLimitError("429 Too Many Requests"))
    before = obs.LLM_ERRORS.labels(kind="rate_limited")._value.get()  # noqa: SLF001
    resp = await client.post(f"{API}/chat", json={"message": "hello"})
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]
    for _ in range(100):
        run = (await client.get(f"{API}/runs/{run_id}")).json()
        if run["status"] in {"failed", "completed"}:
            break
        await asyncio.sleep(0.1)
    assert run["status"] == "failed"
    assert "rate-limited" in run["error"]
    assert "fake:scripted" in run["error"]
    assert "default_model" in run["error"]
    assert obs.LLM_ERRORS.labels(kind="rate_limited")._value.get() == before + 1  # noqa: SLF001


# ── B. every run has a wall clock and a heartbeat ────────────────────


async def test_run_wall_clock_terminates_with_a_truthful_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.orchestrator import runner

    run = await _run_row()

    async def hang(run_id: UUID, resume: Any = None) -> None:
        await asyncio.sleep(30)

    monkeypatch.setattr(runner, "_execute", hang)
    await runner.bounded_execute(run.id, None, wall_clock_s=0.2)
    status, error = await _status(run.id)
    assert status == "failed"
    assert error is not None and "wall clock" in error and "0.2" in error


async def test_every_run_heartbeats_while_it_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.orchestrator import runner

    run = await _run_row()
    assert run.last_heartbeat_at is None
    done = asyncio.Event()

    async def slow(run_id: UUID, resume: Any = None) -> None:
        await done.wait()

    monkeypatch.setattr(runner, "_execute", slow)
    monkeypatch.setattr(runner, "HEARTBEAT_INTERVAL_S", 0.05)
    task = asyncio.create_task(runner.bounded_execute(run.id, None, wall_clock_s=10))
    await asyncio.sleep(0.3)
    async with get_session_factory()() as session:
        row = await session.get(Run, run.id)
        assert row is not None and row.last_heartbeat_at is not None
    done.set()
    await task


async def test_stalled_reaper_covers_chat_runs_too() -> None:
    from app.ambient.execute import reap_stalled_runs

    stale = await _run_row(last_heartbeat_at=datetime.now(UTC) - timedelta(hours=1))
    fresh = await _run_row(last_heartbeat_at=datetime.now(UTC))
    reaped = await reap_stalled_runs(stall_after_s=60)
    assert reaped >= 1
    assert (await _status(stale.id))[0] == "stalled"
    assert (await _status(fresh.id))[0] == "running"


def test_run_wall_clock_setting_is_validated() -> None:
    from app.settings_store import DEFAULTS
    from app.settings_store import validate_updates as validate_settings

    assert DEFAULTS["run_wall_clock_s"] == 900
    assert DEFAULTS["run_max_concurrent"] == 8
    assert DEFAULTS["run_queue_max"] == 32
    assert validate_settings(DEFAULTS, {"run_wall_clock_s": 10})
    assert validate_settings(DEFAULTS, {"run_max_concurrent": 0})
    assert validate_settings(DEFAULTS, {"run_queue_max": -1})
    assert validate_settings(DEFAULTS, {"run_wall_clock_s": 600, "run_max_concurrent": 4}) == []


# ── C. admission control ─────────────────────────────────────────────


async def test_admission_bounds_concurrency_and_sheds_load(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.orchestrator import admission, runner

    await _set(run_max_concurrent=1, run_queue_max=1, default_model="fake:scripted")
    admission.reset()
    release = asyncio.Event()

    async def occupy(run_id: UUID, resume: Any = None) -> None:
        await release.wait()
        async with get_session_factory()() as session:
            row = await session.get(Run, run_id)
            if row is not None:
                row.status = "completed"
                row.final_answer = "done"
                await session.commit()

    monkeypatch.setattr(runner, "_execute", occupy)
    first = (await client.post(f"{API}/chat", json={"message": "one"})).json()["run_id"]
    await asyncio.sleep(0.1)
    second = (await client.post(f"{API}/chat", json={"message": "two"})).json()["run_id"]
    await asyncio.sleep(0.1)
    assert (await _status(UUID(first)))[0] == "running"
    assert (await _status(UUID(second)))[0] == "queued"
    third = await client.post(f"{API}/chat", json={"message": "three"})
    assert third.status_code == 503, third.text
    assert "capacity" in third.json()["detail"]
    assert third.headers.get("retry-after")
    snapshot = admission.snapshot()
    assert snapshot["running"] == 1 and snapshot["queued"] == 1
    release.set()
    for _ in range(50):
        if (await _status(UUID(second)))[0] == "completed":
            break
        await asyncio.sleep(0.05)
    assert (await _status(UUID(first)))[0] == "completed"
    assert (await _status(UUID(second)))[0] == "completed"
    assert admission.snapshot()["running"] == 0


# ── D. the event bus is bounded ──────────────────────────────────────


def test_event_bus_is_bounded_and_read_paths_create_nothing() -> None:
    from app.orchestrator.context import RunEventBus

    bus = RunEventBus(max_runs=3, done_ttl_s=60)
    unknown = uuid4()
    assert bus.is_done(unknown) is False
    assert unknown not in bus._runs  # noqa: SLF001 — the read path must not allocate
    ids = [uuid4() for _ in range(5)]
    for i, rid in enumerate(ids):
        bus.emit(rid, {"type": "token", "payload": {"text": "x"}})
        bus.emit(rid, {"type": "done", "payload": {}}, now=100.0 + i)
    assert len(bus._runs) <= 3  # noqa: SLF001
    assert ids[-1] in bus._runs and ids[0] not in bus._runs  # noqa: SLF001 — oldest done evicted
    # TTL: a done entry older than done_ttl_s is evicted on the next emit
    bus.emit(uuid4(), {"type": "token", "payload": {}}, now=100.0 + 4 + 61)
    assert ids[-1] not in bus._runs  # noqa: SLF001


# ── E. shutdown drains, restart reaps, readiness gates admission ────


async def test_orphaned_runs_are_reaped_at_startup() -> None:
    from app.orchestrator.runner import reap_orphaned_runs

    running = await _run_row("running")
    queued = await _run_row("queued")
    paused = await _run_row("paused_hitl")
    reaped = await reap_orphaned_runs()
    assert reaped == 2
    assert (await _status(running.id)) == ("failed", "orphaned by a restart")
    assert (await _status(queued.id)) == ("failed", "orphaned by a restart")
    assert (await _status(paused.id))[0] == "paused_hitl"  # resumable — untouched


async def test_shutdown_drain_waits_then_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.orchestrator import admission, runner

    admission.reset()
    quick = await _run_row()
    stuck = await _run_row()

    async def finish_quick(run_id: UUID, resume: Any = None) -> None:
        await asyncio.sleep(0.05)
        async with get_session_factory()() as session:
            row = await session.get(Run, run_id)
            if row is not None:
                row.status = "completed"
                await session.commit()

    async def hang(run_id: UUID, resume: Any = None) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:  # mirrors _execute's cancel path
            await runner._finalize_failure(  # noqa: SLF001
                run_id,
                "graph",
                "cancelled",
                runner._SHUTDOWN_REASON or "run cancelled",  # noqa: SLF001
            )
            raise

    calls = {quick.id: finish_quick, stuck.id: hang}

    async def dispatch(run_id: UUID, resume: Any = None) -> None:
        await calls[run_id](run_id, resume)

    monkeypatch.setattr(runner, "_execute", dispatch)
    runner.start_run_task(quick.id)
    runner.start_run_task(stuck.id)
    await asyncio.sleep(0.02)
    report = await runner.drain_running_tasks(grace_s=0.3)
    assert report["finished"] >= 1 and report["cancelled"] >= 1
    assert (await _status(quick.id))[0] == "completed"
    status, error = await _status(stuck.id)
    assert status == "cancelled"
    # the record says WHY: the shutdown and its grace, not a user's Stop
    assert error is not None and "cancelled by shutdown" in error and "0.3" in error
    assert runner._SHUTDOWN_REASON is None  # noqa: SLF001 — a later Stop is a user's Stop again
    assert not runner.RUNNING_TASKS


async def test_readiness_gates_admission(client: AsyncClient) -> None:
    from app.orchestrator import admission

    admission.reset()
    assert (await client.get("/ready")).status_code == 200
    admission.set_accepting(False)
    try:
        assert (await client.get("/ready")).status_code == 503
        resp = await client.post(f"{API}/chat", json={"message": "hi"})
        assert resp.status_code == 503 and "not accepting" in resp.json()["detail"]
    finally:
        admission.set_accepting(True)


# ── F. no session spans a provider call ─────────────────────────────


async def test_session_tracker_counts_open_sessions() -> None:
    assert app_db.open_sessions() == 0
    async with get_session_factory()() as session:
        await session.execute(select(Run).limit(1))
        assert app_db.open_sessions() == 1
    assert app_db.open_sessions() == 0


async def test_memory_write_never_holds_a_session_across_the_embedding_call(
    client: AsyncClient,
) -> None:
    """spec §16.2 / arch-H15: the embedding is computed BEFORE the write
    transaction opens. The fake provider refuses a call made with a session
    open, so a regression fails here instead of holding a pooled connection
    for the life of a network round trip."""
    from app.memory.store import remember

    await _set(memory_enabled=True, embedding_model="fake:scripted")
    fake_llm.set_strict_sessions(True)
    try:
        row = await remember(text="bounded write", kind="fact", source="user_stated")
    finally:
        fake_llm.set_strict_sessions(False)
    async with get_session_factory()() as session:
        from app.models import MemoryEmbedding

        vec = (
            await session.execute(select(MemoryEmbedding).where(MemoryEmbedding.ref_id == row.id))
        ).scalar_one_or_none()
        assert vec is not None


async def test_digest_never_holds_a_session_across_the_model_call(client: AsyncClient) -> None:
    from app.memory.episodic import digest_run

    await _set(memory_enabled=True, embedding_model="fake:scripted", default_model="fake:scripted")
    run = await _run_row("completed", final_answer="the capital of Portugal is Lisbon")
    fake_llm.push_ai("digest: capital of Portugal answered")
    fake_llm.set_strict_sessions(True)
    try:
        digest = await digest_run(run.id)
    finally:
        fake_llm.set_strict_sessions(False)
    assert digest is not None


async def test_drain_claims_then_commits_then_processes(client: AsyncClient) -> None:
    """arch-H8: the processor (which may call a model) runs with NO row
    lock and NO session open; the claim is committed first and the verdict
    written back afterwards."""
    from app.ambient.drain import RECLAIM_AFTER_S, drain_once, register_processor
    from app.ambient.store import emit_event

    await _set(ambient_enabled=True)
    seen: list[dict[str, Any]] = []

    async def processor(event: AmbientEvent) -> tuple[str, str]:
        async with get_session_factory()() as session:
            fresh = await session.get(AmbientEvent, event.id)
            claimed = fresh.verdict if fresh else None
        seen.append({"open_sessions": app_db.open_sessions(), "claimed_as": claimed})
        return ("held", "processed outside the lock")

    register_processor(processor)
    try:
        event = await emit_event(kind="m51_claim", source="manual", payload={})
        assert event is not None
        handled = await drain_once()
        assert handled == 1
        assert seen and seen[0]["open_sessions"] == 0
        assert seen[0]["claimed_as"] == "processing"  # the claim was COMMITTED before processing
        async with get_session_factory()() as session:
            row = await session.get(AmbientEvent, event.id)
            assert row is not None and row.verdict == "held" and row.processed_at is not None
        # a claim abandoned by a dead process is reclaimed after RECLAIM_AFTER_S
        stuck = await emit_event(kind="m51_stuck", source="manual", payload={})
        assert stuck is not None
        async with get_session_factory()() as session:
            await session.execute(
                update(AmbientEvent)
                .where(AmbientEvent.id == stuck.id)
                .values(
                    verdict="processing",
                    processed_at=datetime.now(UTC) - timedelta(seconds=RECLAIM_AFTER_S + 5),
                )
            )
            await session.commit()
        assert await drain_once() == 1
        async with get_session_factory()() as session:
            row = await session.get(AmbientEvent, stuck.id)
            assert row is not None and row.verdict == "held"
    finally:
        register_processor(None)


# ── G. delivery retries with backoff and dead-letters ────────────────


async def _delivery(**kw: Any) -> Delivery:
    async with get_session_factory()() as session:
        row = Delivery(title="m51 alert", body="body", tier=0, urgency=4, **kw)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def test_external_send_retries_with_backoff_then_dead_letters(client: AsyncClient) -> None:
    from app.ambient import channels
    from app.ambient.channels import (
        MAX_SEND_ATTEMPTS,
        dispatch_delivered,
        register_channel_adapter,
        retry_external_sends,
    )

    calls = {"flaky": 0, "dead": 0}

    async def flaky(mode: str, rows: list[Delivery]) -> None:
        calls["flaky"] += 1
        if calls["flaky"] < 3:
            raise RuntimeError("smtp down")

    async def dead(mode: str, rows: list[Delivery]) -> None:
        calls["dead"] += 1
        raise RuntimeError("gateway gone")

    register_channel_adapter("flaky", flaky)  # the routing validator needs them registered
    register_channel_adapter("dead", dead)
    try:
        await _set(
            ambient_enabled=True, ambient_channels={"interrupt": ["in_app", "flaky", "dead"]}
        )
        row = await _delivery(delivered_at=datetime.now(UTC), channel="interrupt")
        await dispatch_delivered("interrupt", [row])
        async with get_session_factory()() as session:
            fresh = await session.get(Delivery, row.id)
            assert fresh is not None and fresh.external is not None
            entry = fresh.external["flaky"]
            assert entry["ok"] is False and entry["attempts"] == 1 and entry["next_attempt_at"]
            assert entry["dead"] is False
        # not due yet → nothing happens
        assert await retry_external_sends(now=datetime.now(UTC)) == 0
        # step the clock past the backoffs until the flaky channel succeeds
        now = datetime.now(UTC)
        for _ in range(MAX_SEND_ATTEMPTS):
            now += timedelta(hours=1)
            await retry_external_sends(now=now)
        async with get_session_factory()() as session:
            fresh = await session.get(Delivery, row.id)
            assert fresh is not None and fresh.external is not None
            assert fresh.external["flaky"]["ok"] is True
            assert fresh.external["flaky"]["attempts"] == 3
            assert fresh.external["dead"]["ok"] is False
            assert fresh.external["dead"]["dead"] is True
            assert fresh.external["dead"]["attempts"] == MAX_SEND_ATTEMPTS
        # dead-lettered: no more attempts however much time passes
        before = calls["dead"]
        await retry_external_sends(now=now + timedelta(days=1))
        assert calls["dead"] == before
    finally:
        channels._ADAPTERS.pop("flaky", None)  # noqa: SLF001
        channels._ADAPTERS.pop("dead", None)  # noqa: SLF001


async def test_flush_dispatches_before_it_commits(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatch-then-commit: at the moment the channel fires, the row is not
    yet committed as delivered — a crash between the two re-delivers rather
    than silently losing the toast."""
    from app.ambient import channels, deliver

    observed: list[datetime | None] = []

    async def probe(mode: str, rows: list[Delivery]) -> None:
        async with get_session_factory()() as session:
            fresh = await session.get(Delivery, rows[0].id)
            observed.append(fresh.delivered_at if fresh else None)

    channels.register_channel_adapter("probe", probe)
    try:
        await _set(
            ambient_enabled=True,
            ambient_quiet_hours=[],  # an interrupt at night would demote, not deliver
            ambient_channels={"interrupt": ["in_app", "probe"]},
        )
        row = await _delivery()
        await deliver.flush_deliveries()
        assert observed == [None], "the channel saw an UNCOMMITTED delivery — dispatch ran first"
        async with get_session_factory()() as session:
            fresh = await session.get(Delivery, row.id)
            assert fresh is not None and fresh.delivered_at is not None
            assert fresh.external is not None and fresh.external["probe"]["ok"] is True
    finally:
        channels._ADAPTERS.pop("probe", None)  # noqa: SLF001


# ── H. registry cache fails open ─────────────────────────────────────


async def test_registry_cache_fails_open_to_postgres(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.registry_cache import get_cache, reset_cache

    reset_cache()
    cache = get_cache()
    cache._mode = "redis"  # noqa: SLF001

    async def broken() -> Any:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(cache, "_get_redis", broken)
    before = obs.CACHE_DEGRADED.labels(backend="redis")._value.get()  # noqa: SLF001
    rows = await cache.tools(exposed_only=False)
    assert isinstance(rows, list)  # served from Postgres, no raise
    assert obs.CACHE_DEGRADED.labels(backend="redis")._value.get() == before + 1  # noqa: SLF001
    reset_cache()


# ── I. atomic token totals; newest fact wins ─────────────────────────


async def test_token_totals_increment_atomically() -> None:
    from app.orchestrator.recorder import RunRecorder

    run = await _run_row()
    recorder = RunRecorder(run.id)
    steps = [await recorder.start_step("skill", tier="skill") for _ in range(40)]
    await asyncio.gather(
        *(recorder.finish_step(s, input_tokens=10, output_tokens=1) for s in steps)
    )
    async with get_session_factory()() as session:
        row = await session.get(Run, run.id)
        assert row is not None
        assert (row.total_input_tokens, row.total_output_tokens) == (400, 40)


async def test_contradiction_sweep_keeps_the_newest_fact(client: AsyncClient) -> None:
    from app.memory.lifecycle import contradiction_sweep
    from app.memory.store import remember

    await _set(memory_enabled=True)
    old = await remember(
        text="the office is in Porto",
        kind="fact",
        source="user_stated",
        entity_key="office.location",
        valid_from=datetime.now(UTC) - timedelta(days=30),
    )
    new = await remember(
        text="the office is in Lisbon",
        kind="fact",
        source="user_stated",
        entity_key="office.location",
        valid_from=datetime.now(UTC),
    )
    assert await contradiction_sweep() == 1
    async with get_session_factory()() as session:
        assert (await session.get(Memory, new.id)).status == "active"  # type: ignore[union-attr]
        assert (await session.get(Memory, old.id)).status == "quarantined"  # type: ignore[union-attr]


def test_start_run_task_signature_is_admission_aware() -> None:
    from app.orchestrator.runner import start_run_task

    assert "shed_if_full" in inspect.signature(start_run_task).parameters


async def _unused(session: Any, step: RunStep) -> None:  # keeps the import meaningful for mypy
    pass
