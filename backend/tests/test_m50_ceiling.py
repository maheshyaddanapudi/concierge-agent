"""M50 — the ceiling (docs/research/prod_hardening/PLAN.md M50).

The M49 baseline measured four ways the shipped stack falls over first:
streams hold the connection pool, list endpoints scale with the table,
memory visibility is duplicated across retrieval paths, and one malformed
trigger wedges the ambient tick. Plus the timezone promise quiet hours
make and break for everyone off UTC. These tests pin the fixes.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.auth import bind_run_owner
from app.config import AppConfig, get_config
from app.db import get_engine, get_session_factory
from app.llm import fake as fake_llm
from app.models import Conversation, Memory, Routine, Run, RunStep
from app.settings_store import update_settings
from tests.factory_helpers import create_skill, create_sub_agent

pytestmark = pytest.mark.anyio

API = "/api/v1"


async def _set(**kv: Any) -> None:
    async with get_session_factory()() as session:
        await update_settings(session, kv)


async def _wait_run(client: AsyncClient, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + 20
    run: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        run = (await client.get(f"{API}/runs/{run_id}")).json()
        if run["status"] in statuses:
            return dict(run)
        await asyncio.sleep(0.1)
    raise AssertionError(f"run did not reach {statuses}; last: {run.get('status')}")


# ── A. the connection pool is explicit and the stream does not hold it ──


def test_pool_budget_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT"):
        monkeypatch.setenv(var, "")
    cfg = AppConfig(_env_file=None)
    assert (cfg.db_pool_size, cfg.db_max_overflow, cfg.db_pool_timeout) == (5, 10, 30)
    monkeypatch.setenv("DB_POOL_SIZE", "20")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "5")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "7")
    cfg = AppConfig(_env_file=None)
    assert (cfg.db_pool_size, cfg.db_max_overflow, cfg.db_pool_timeout) == (20, 5, 7)


def test_engine_is_built_from_the_pool_budget() -> None:
    pool = get_engine().pool
    cfg = get_config()
    assert pool.size() == cfg.db_pool_size
    assert pool._max_overflow == cfg.db_max_overflow  # noqa: SLF001 - pool exposes no getter
    assert pool._timeout == cfg.db_pool_timeout  # noqa: SLF001


async def _paused_run(client: AsyncClient) -> str:
    """A run parked at a HITL gate — the shape that keeps a stream open."""
    await _set(default_model="fake:scripted", formatter_enabled=False, orchestrator_mode="graph")
    s1 = await create_skill(name=f"pre-{uuid4().hex[:4]}")
    s2 = await create_skill(name=f"post-{uuid4().hex[:4]}")
    agent = await create_sub_agent(
        {
            "nodes": [
                {"id": "work", "type": "skill", "skill_id": str(s1.id)},
                {"id": "gate", "type": "hitl", "prompt": "Save the result?"},
                {"id": "save", "type": "skill", "skill_id": str(s2.id)},
            ],
            "edges": [
                {"from": "START", "to": "work"},
                {"from": "work", "to": "gate"},
                {"from": "gate", "to": "save"},
                {"from": "save", "to": "END"},
            ],
        },
        name=f"hitl-agent-{uuid4().hex[:4]}",
    )
    fake_llm.push_ai(
        "",
        tool_calls=[
            {
                "name": "PlannerOutput",
                "args": {
                    "entries": [
                        {
                            "id": "s1",
                            "capability": {"type": "sub_agent", "id": str(agent.id)},
                            "task": "work then save",
                            "depends_on": [],
                        }
                    ],
                    "direct_answer": None,
                    "no_confident_match": False,
                },
                "id": f"p{uuid4().hex[:6]}",
            }
        ],
    )
    fake_llm.push_ai("work output")
    resp = await client.post(f"{API}/chat", json={"message": "hitl flow"})
    assert resp.status_code == 201, resp.text
    run_id = str(resp.json()["run_id"])
    run = await _wait_run(client, run_id, {"paused_hitl", "failed"})
    assert run["status"] == "paused_hitl", run["error"]
    return run_id


async def test_chat_stream_holds_no_pooled_connection_while_open(client: AsyncClient) -> None:
    """arch-C1: the SSE endpoint used to keep a request-scoped session (and
    its connection) for the life of the stream — 15 open tabs exhausted the
    pool. It now reads what it needs, releases, then streams."""
    from app.api.chat import chat_stream

    assert "session" not in inspect.signature(chat_stream).parameters
    run_id = await _paused_run(client)
    pool = get_engine().pool
    responses = [await chat_stream(UUID(run_id)) for _ in range(3)]
    assert pool.checkedout() == 0
    iterators = [r.body_iterator for r in responses]
    for it in iterators:
        first = await it.__anext__()
        assert first["event"] == "run_status"  # replayed history arrives connection-free
    assert pool.checkedout() == 0
    for it in iterators:
        await it.aclose()
    await client.post(f"{API}/runs/{run_id}/cancel")


async def test_chat_stream_unknown_run_is_404(client: AsyncClient) -> None:
    resp = await client.get(f"{API}/chat/stream/{uuid4()}")
    assert resp.status_code == 404


# ── B. list endpoints page; children load explicitly; hot paths indexed ──


async def _seed_runs(n_conversations: int, runs_each: int) -> list[UUID]:
    ids: list[UUID] = []
    async with get_session_factory()() as session:
        base = datetime.now(UTC) - timedelta(hours=1)
        k = 0
        for c in range(n_conversations):
            conv = Conversation(title=f"paged conv {c}")
            session.add(conv)
            await session.flush()
            for _ in range(runs_each):
                k += 1
                run = Run(
                    conversation_id=conv.id,
                    chat_message=f"paged q{k}",
                    status="completed",
                    final_answer=f"a{k}",
                    started_at=base + timedelta(seconds=k),
                )
                session.add(run)
                await session.flush()
                session.add(RunStep(run_id=run.id, step_type="plan", status="completed"))
                ids.append(run.id)
        await session.commit()
    return ids


async def test_runs_list_pages_newest_first_with_total(client: AsyncClient) -> None:
    ids = await _seed_runs(3, 3)  # 9 runs, k=1..9 with increasing started_at
    page = await client.get(f"{API}/runs?limit=4")
    assert page.status_code == 200
    assert page.headers["x-total-count"] == "9"
    rows = page.json()
    assert [r["chat_message"] for r in rows] == ["paged q9", "paged q8", "paged q7", "paged q6"]
    nxt = (await client.get(f"{API}/runs?limit=4&offset=4")).json()
    assert [r["chat_message"] for r in nxt] == ["paged q5", "paged q4", "paged q3", "paged q2"]
    last = (await client.get(f"{API}/runs?limit=4&offset=8")).json()
    assert [r["chat_message"] for r in last] == ["paged q1"]
    assert {r["id"] for r in rows} | {r["id"] for r in nxt} | {r["id"] for r in last} == {
        str(i) for i in ids
    }
    # bounds are enforced, and the list never carries step bodies
    assert (await client.get(f"{API}/runs?limit=0")).status_code == 422
    assert (await client.get(f"{API}/runs?limit=501")).status_code == 422
    assert (await client.get(f"{API}/runs?offset=-1")).status_code == 422
    assert "steps" not in rows[0]
    everything = (await client.get(f"{API}/runs")).json()
    assert len(everything) == 9  # default page (50) covers a small table


async def test_conversations_list_pages_with_aggregate_run_count(client: AsyncClient) -> None:
    await _seed_runs(3, 2)
    page = await client.get(f"{API}/conversations?limit=2")
    assert page.status_code == 200
    assert page.headers["x-total-count"] == "3"
    rows = page.json()
    assert len(rows) == 2
    assert all(r["run_count"] == 2 for r in rows)
    rest = (await client.get(f"{API}/conversations?limit=2&offset=2")).json()
    assert len(rest) == 1 and rest[0]["run_count"] == 2
    assert (await client.get(f"{API}/conversations?limit=9999")).status_code == 422


def test_child_relationships_are_loaded_explicitly() -> None:
    """code-H1: lazy='selectin' loaded every run of every conversation (and
    every step of every run) on any access. The relationships now refuse
    implicit loads; the call sites that need children ask for them."""
    assert Conversation.runs.property.lazy == "raise"
    assert Run.steps.property.lazy == "raise"


async def test_detail_endpoints_still_carry_children(client: AsyncClient) -> None:
    ids = await _seed_runs(1, 2)
    run = (await client.get(f"{API}/runs/{ids[0]}")).json()
    assert [s["step_type"] for s in run["steps"]] == ["plan"]
    conv = (await client.get(f"{API}/conversations/{run['conversation_id']}")).json()
    assert len(conv["runs"]) == 2
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]


async def test_hot_path_indexes_exist() -> None:
    """arch-C2: 23 migrations and not one FK index on the run tables."""
    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tablename, indexdef FROM pg_indexes "
                    "WHERE tablename IN ('runs', 'run_steps', 'tools')"
                )
            )
        ).all()
    defs = [(str(t), str(d)) for t, d in rows]
    for table, column in (
        ("runs", "conversation_id"),
        ("runs", "status"),
        ("runs", "started_at"),
        ("run_steps", "run_id"),
        ("tools", "mcp_server_id"),
    ):
        assert any(t == table and f"({column})" in d for t, d in defs), (table, column, defs)


def test_index_migration_is_shipped() -> None:
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = "\n".join(p.read_text() for p in versions.glob("*.py"))
    for name in (
        "runs_conversation_idx",
        "runs_status_idx",
        "runs_started_at_idx",
        "run_steps_run_idx",
        "tools_mcp_server_idx",
    ):
        assert name in sources, f"migration for {name} missing"


# ── C. one memory visibility predicate ────────────────────────────────


async def _pinned(text_: str, **kw: Any) -> Memory:
    from app.memory.store import remember

    row = await remember(text=text_, kind="fact", source="user_stated", **kw)
    async with get_session_factory()() as session:
        await session.execute(update(Memory).where(Memory.id == row.id).values(pinned=True))
        await session.commit()
    return row


async def test_pinned_rows_respect_project_and_conversation(client: AsyncClient) -> None:
    """code-H5: pinned selection ignored project_key (a live leak) and
    conversation scope was filtered in Python after a global query."""
    from app.memory.rank import pinned_memories

    await _set(memory_enabled=True)
    async with get_session_factory()() as session:
        a, b = Conversation(title="conv a"), Conversation(title="conv b")
        session.add_all([a, b])
        await session.commit()
        conv_a, conv_b = a.id, b.id
    g = await _pinned("global pinned fact")
    p = await _pinned("apollo pinned fact", scope="project", project_key="apollo")
    c = await _pinned("conversation pinned fact", scope="conversation", conversation_id=conv_a)

    def ids(rows: list[Memory]) -> set[UUID]:
        return {m.id for m in rows}

    assert ids(await pinned_memories(conversation_id=None, project_key=None)) == {g.id}
    assert ids(await pinned_memories(conversation_id=conv_a, project_key="apollo")) == {
        g.id,
        p.id,
        c.id,
    }
    assert ids(await pinned_memories(conversation_id=conv_b, project_key="artemis")) == {g.id}


@pytest.fixture
def auth_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    get_config.cache_clear()
    yield
    bind_run_owner(None)
    get_config.cache_clear()


async def test_pinned_rows_respect_tenancy(client: AsyncClient, auth_on: Any) -> None:
    """The dormant tenancy leak: pinned rows never checked user_id."""
    from app.memory.rank import pinned_memories

    await _set(memory_enabled=True)
    user_a, user_b = uuid4(), uuid4()
    mine = await _pinned("user a pinned", user_id=user_a)
    shared = await _pinned("unowned pinned")  # NULL owner stays visible to all (§18.8)
    bind_run_owner(user_b)
    visible = {m.id for m in await pinned_memories()}
    assert mine.id not in visible and shared.id in visible
    bind_run_owner(user_a)
    visible = {m.id for m in await pinned_memories()}
    assert mine.id in visible and shared.id in visible


async def test_recall_and_pinned_share_one_predicate_builder(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The contract test the duplication deserved: both retrieval paths go
    through the same visibility builder, so a future scope rule cannot be
    added to one and forgotten in the other."""
    from app.memory import rank

    await _set(memory_enabled=True)
    await _pinned("shared builder fact")
    calls: list[dict[str, Any]] = []
    real = rank.visibility_sql

    def spy(**kw: Any) -> Any:
        calls.append(kw)
        return real(**kw)

    monkeypatch.setattr(rank, "visibility_sql", spy)
    await rank.recall("shared builder fact", project_key="apollo", bump_access=False)
    assert len(calls) == 1 and calls[0]["project_key"] == "apollo"
    await rank.pinned_memories(conversation_id=None, project_key="apollo")
    assert len(calls) == 2 and calls[1]["project_key"] == "apollo"


# ── D. triggers are typed at the boundary; a broken one cannot wedge the tick ──


async def _routine_payload(triggers: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": f"r-{uuid4().hex[:6]}", "prompt": "do the thing", "triggers": triggers}


async def test_routine_triggers_are_validated_at_the_api(client: AsyncClient) -> None:
    await _set(ambient_enabled=True)
    bad = [
        [{"type": "once", "at": "not-a-date"}],
        [{"type": "interval", "seconds": 5}],
        [{"type": "cron", "cron": "bogus"}],
        [{"type": "webhook", "filters": [{"field": "x", "op": "nope", "value": "1"}]}],
        [{"type": "teleport"}],
        [{"type": "interval", "seconds": 3600, "surprise": 1}],
        ["not-an-object"],
    ]
    for triggers in bad:
        resp = await client.post(f"{API}/routines", json=await _routine_payload(triggers))
        assert resp.status_code == 422, (triggers, resp.text)
        assert "trigger" in resp.text.lower()
    good = [
        {"type": "interval", "seconds": 3600},
        {"type": "cron", "cron": "0 9 * * *"},
        {"type": "once", "at": "2030-01-01T09:00:00+00:00"},
        {"type": "webhook", "filters": [{"field": "payload.kind", "op": "equals", "value": "x"}]},
        {"type": "webhook"},
    ]
    resp = await client.post(f"{API}/routines", json=await _routine_payload(good))
    assert resp.status_code == 201, resp.text
    routine_id = resp.json()["id"]
    resp = await client.patch(
        f"{API}/routines/{routine_id}", json={"triggers": [{"type": "cron", "cron": "* * *"}]}
    )
    assert resp.status_code == 422
    resp = await client.patch(
        f"{API}/routines/{routine_id}", json={"triggers": [{"type": "interval", "seconds": 120}]}
    )
    assert resp.status_code == 200


async def test_malformed_trigger_is_quarantined_and_the_tick_keeps_ticking(
    client: AsyncClient,
) -> None:
    """code-H4: one bad `once.at` raised out of evaluate_schedules and no
    routine after it was evaluated. Now the broken routine accrues failures,
    is set to error after three, and the healthy routine fires regardless."""
    from app.ambient.triggers import QUARANTINE_AFTER, evaluate_schedules
    from app.models import AmbientEvent

    await _set(ambient_enabled=True)
    async with get_session_factory()() as session:
        broken = Routine(name="a-broken", prompt="p", triggers=[{"type": "once", "at": "garbage"}])
        healthy = Routine(
            name="b-healthy", prompt="p", triggers=[{"type": "interval", "seconds": 3600}]
        )
        session.add_all([broken, healthy])
        await session.commit()
        broken_id, healthy_id = broken.id, healthy.id
    now = datetime.now(UTC)
    for i in range(QUARANTINE_AFTER):
        await evaluate_schedules(now=now + timedelta(minutes=i))
    async with get_session_factory()() as session:
        events = list(
            (
                await session.execute(
                    select(AmbientEvent).where(AmbientEvent.routine_id == healthy_id)
                )
            ).scalars()
        )
        assert len(events) == 1, "the healthy routine fired exactly once"
        row = await session.get(Routine, broken_id)
        assert row is not None
        assert row.status == "error"
        assert row.consecutive_failures >= QUARANTINE_AFTER
        assert "trigger" in str(row.status_reason).lower()


async def test_tick_evaluators_are_isolated_and_bounded() -> None:
    from app import obs
    from app.ambient.drain import run_evaluator

    async def boom() -> int:
        raise RuntimeError("evaluator exploded")

    async def slow() -> int:
        await asyncio.sleep(5)
        return 1

    async def fine() -> int:
        return 7

    before_err = obs.AMBIENT_EVALUATOR_ERRORS.labels(evaluator="boom", kind="error")._value.get()  # noqa: SLF001
    before_to = obs.AMBIENT_EVALUATOR_ERRORS.labels(evaluator="slow", kind="timeout")._value.get()  # noqa: SLF001
    assert await run_evaluator("boom", boom) is None
    assert await run_evaluator("slow", slow, timeout_s=0.05) is None
    assert await run_evaluator("fine", fine) == 7
    assert (
        obs.AMBIENT_EVALUATOR_ERRORS.labels(evaluator="boom", kind="error")._value.get()
        == before_err + 1
    )  # noqa: SLF001
    assert (
        obs.AMBIENT_EVALUATOR_ERRORS.labels(evaluator="slow", kind="timeout")._value.get()
        == before_to + 1
    )  # noqa: SLF001


# ── E. quiet hours and digest times resolve in the user's zone ──────────


async def test_ambient_timezone_setting(client: AsyncClient) -> None:
    settings = (await client.get(f"{API}/settings")).json()
    assert settings["ambient_timezone"] == "UTC"
    resp = await client.patch(f"{API}/settings", json={"ambient_timezone": "Europe/Lisbon"})
    assert resp.status_code == 200 and resp.json()["ambient_timezone"] == "Europe/Lisbon"
    resp = await client.patch(f"{API}/settings", json={"ambient_timezone": "Mars/Olympus"})
    assert resp.status_code == 422 and "ambient_timezone" in resp.text
    resp = await client.patch(f"{API}/settings", json={"ambient_timezone": 7})
    assert resp.status_code == 422


def test_quiet_hours_resolve_in_the_configured_zone() -> None:
    from app.ambient.deliver import in_quiet_hours

    ranges = ["22:00", "07:00"]
    now = datetime(2026, 9, 1, 6, 30, tzinfo=UTC)  # 06:30 UTC
    assert in_quiet_hours(now, ranges) is True  # default zone is UTC: 06:30 is quiet
    assert in_quiet_hours(now, ranges, "Europe/Lisbon") is False  # 07:30 local: morning
    assert in_quiet_hours(now, ranges, "America/New_York") is True  # 02:30 local: night
    assert in_quiet_hours(now, ranges, "Asia/Tokyo") is False  # 15:30 local: afternoon


async def test_digest_due_resolves_in_the_configured_zone(client: AsyncClient) -> None:
    from app.ambient.deliver import _digest_due

    now = datetime(2026, 9, 1, 8, 30, tzinfo=UTC)  # 09:30 in Lisbon, 08:30 in UTC
    async with get_session_factory()() as session:
        assert await _digest_due(session, now, ["09:00"], tz="Europe/Lisbon") is True
        assert await _digest_due(session, now, ["09:00"], tz="UTC") is False
        assert await _digest_due(session, now, ["09:00"]) is False


async def test_effective_settings_carry_the_zone(client: AsyncClient) -> None:
    from app.ambient.deliver import effective_ambient_settings

    await _set(ambient_timezone="Europe/Lisbon")
    eff = await effective_ambient_settings(None)
    assert eff["ambient_timezone"] == "Europe/Lisbon"
