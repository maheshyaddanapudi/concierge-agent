"""Retention for the unbounded tables (M53, arch-M6).

`ambient_events`, `deliveries`, `ambient_policies`, `pattern_instances`,
`a2a_tasks` and `auth_sessions` had no retention job, no TTL and no purge
surface: at a year of operation the two ambient ledgers dominate the
database and slow every tick, and the only way to trim them was manual SQL.

The run ledger is the same shape and was missed: `runs`, `run_steps` and the
LangGraph checkpoint tables grow with every chat turn, every ambient fire
and every eval case, and only a full history purge (spec §8.7, all or
nothing) could trim them. They join the job on the same terms — own gate,
own window, born dark — with the run lifecycle respected: a run that is
queued, running or paused for approval is never touched at any age, and a
paused run's checkpoints are what resume it, so they survive too.

Each table now has a purge with its own window and — per the §3.7.1
discipline M48 established — its own gate, ENFORCED INSIDE THE PURGE
FUNCTION, so no call path (the hourly tick, the operator's "run now", a
test) deletes anything behind a switch that is off. Every purge deletes only
rows the system is finished with: processed events, delivered or superseded
deliveries, superseded policy rows (the latest row per category is the live
policy and is never touched), matched or expired pattern instances,
terminal A2A tasks, and sessions past their expiry. Pending, armed, open and
current rows survive whatever their age.

Deleting is destructive, so every gate but one is born dark; only the
expired-session sweep defaults on, because the login path already deleted
expired sessions opportunistically before M53. The job is advisory-locked
(one replica works) and reports what it deleted through
`concierge_retention_deleted_total{table}`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Select, and_, delete, func, select, text

from app import obs
from app.db import get_session_factory
from app.models import (
    A2A_TERMINAL_STATES,
    A2ATask,
    AmbientEvent,
    AmbientPolicy,
    AuthSession,
    Delivery,
    PatternInstance,
    Run,
    RunStep,
)

logger = structlog.get_logger("retention")

# a run that may still execute or resume: never trimmed, whatever its age
LIVE_RUN_STATES: tuple[str, ...] = ("queued", "running", "paused_hitl")
# the three LangGraph checkpointer tables (owned by AsyncPostgresSaver.setup(),
# outside app metadata) — all keyed by thread_id, which is the run id for the
# orchestrator thread and "run_id:entry_id" for a worker thread
CHECKPOINT_TABLES: tuple[str, ...] = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")

RETENTION_TABLES: tuple[str, ...] = (
    "ambient_events",
    "deliveries",
    "ambient_policies",
    "pattern_instances",
    "a2a_tasks",
    "auth_sessions",
    # the run ledger, purged narrowest-first so a checkpoint or a step is
    # never orphaned by its run disappearing under a different window
    "checkpoints",
    "run_steps",
    "runs",
)
RETENTION_GATES: dict[str, str] = {t: f"retention_{t}_enabled" for t in RETENTION_TABLES}
RETENTION_WINDOWS: dict[str, str] = {t: f"retention_{t}_days" for t in RETENTION_TABLES}

# a dedicated advisory-lock pair: never the memory jobs' classid (42016) nor
# the ambient leader's (427017) — part of the cross-replica contract
RETENTION_LOCK_CLASSID = 427018
RETENTION_LOCK_OBJID = 1

RETENTION_INTERVAL_S = 3600.0
_BATCH = 5000
# runs are batched smaller: each one drags its steps and its checkpoints
_RUN_BATCH = 500
_LAST_RUN: float | None = None


def _eligible(table: str, cutoff: datetime) -> Select[tuple[Any]]:
    """Ids of the rows retention may delete for `table` — rows the system is
    finished with AND older than the window. Everything else survives."""
    if table == "ambient_events":
        return select(AmbientEvent.id).where(
            AmbientEvent.verdict.is_not(None), AmbientEvent.received_at < cutoff
        )
    if table == "deliveries":
        return select(Delivery.id).where(
            (Delivery.delivered_at.is_not(None)) | (Delivery.superseded_by.is_not(None)),
            Delivery.created_at < cutoff,
        )
    if table == "ambient_policies":
        # the newest row per (category, owner) IS the policy — keep it at any age
        latest = (
            select(AmbientPolicy.id)
            .distinct(AmbientPolicy.category, AmbientPolicy.user_id)
            .order_by(
                AmbientPolicy.category, AmbientPolicy.user_id, AmbientPolicy.created_at.desc()
            )
        )
        return select(AmbientPolicy.id).where(
            AmbientPolicy.created_at < cutoff, AmbientPolicy.id.not_in(latest)
        )
    if table == "pattern_instances":
        return select(PatternInstance.id).where(
            PatternInstance.state != "armed", PatternInstance.created_at < cutoff
        )
    if table == "a2a_tasks":
        return select(A2ATask.id).where(
            A2ATask.state.in_(sorted(A2A_TERMINAL_STATES)), A2ATask.updated_at < cutoff
        )
    if table == "auth_sessions":
        return select(AuthSession.id).where(AuthSession.expires_at < cutoff)
    if table == "runs":
        return select(Run.id).where(_trimmable_runs(cutoff))
    if table == "run_steps":
        # steps of a trimmable run: the summary row may outlive its trace
        # under a shorter step window, never the other way round
        return select(RunStep.id).where(
            RunStep.run_id.in_(select(Run.id).where(_trimmable_runs(cutoff)))
        )
    raise KeyError(f"unknown retention table {table!r}")


def _trimmable_runs(cutoff: datetime) -> Any:
    """A run the system is finished with: it reached a terminal status and
    finished before the cutoff. Queued, running and paused runs survive at
    any age — a paused run is still waiting on a human."""
    return and_(
        Run.status.not_in(LIVE_RUN_STATES),
        Run.finished_at.is_not(None),
        Run.finished_at < cutoff,
    )


_MODELS: dict[str, Any] = {
    "ambient_events": AmbientEvent,
    "deliveries": Delivery,
    "ambient_policies": AmbientPolicy,
    "pattern_instances": PatternInstance,
    "a2a_tasks": A2ATask,
    "auth_sessions": AuthSession,
    "runs": Run,
    "run_steps": RunStep,
}


async def _checkpoint_thread_sql(session: Any, verb: str, cutoff: datetime) -> int:
    """`verb` is COUNT or DELETE over the checkpoint tables, matched by the
    run id their thread_id carries. Threads whose run is gone, live or young
    are left alone; the tables may not exist yet (no run has ever executed),
    which is not an error."""
    live = ", ".join(f"'{state}'" for state in LIVE_RUN_STATES)  # module constant, not input
    run_ids = (
        f"SELECT id::text FROM runs WHERE status NOT IN ({live}) "  # noqa: S608 - see above
        "AND finished_at IS NOT NULL AND finished_at < :cutoff"
    )
    params: dict[str, Any] = {"cutoff": cutoff}
    total = 0
    # COUNT reports the parent table only: the other two are purged with it,
    # by the same threads, so counting all three would triple one run's cost
    tables = CHECKPOINT_TABLES if verb == "DELETE" else ("checkpoints",)
    for table in tables:
        exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": table})
        if exists.scalar_one_or_none() is None:
            continue
        # split_part gives the run id for both thread shapes: "<run_id>" and
        # "<run_id>:<entry_id>"
        where = f"WHERE split_part(thread_id, ':', 1) IN ({run_ids})"  # noqa: S608 - fixed SQL
        if verb == "DELETE":
            result = await session.execute(
                text(f"DELETE FROM {table} {where}"),  # noqa: S608 - fixed table names
                params,
            )
            total += int(result.rowcount or 0)
        else:
            count = await session.execute(
                text(f"SELECT count(*) FROM {table} {where}"),  # noqa: S608 - fixed table names
                params,
            )
            total += int(count.scalar_one())
    return total


async def _setting(key: str) -> Any:
    from app.registry_cache import get_cache

    return await get_cache().setting(key)


async def gate_open(table: str) -> bool:
    return bool(await _setting(RETENTION_GATES[table]))


async def window_days(table: str) -> int:
    return max(int(await _setting(RETENTION_WINDOWS[table]) or 1), 1)


async def _cutoff(table: str, now: datetime) -> datetime:
    return now - timedelta(days=await window_days(table))


async def eligible_counts(now: datetime | None = None) -> dict[str, int]:
    """How many rows each purge WOULD delete right now — counted whether or
    not the gate is on, so the Settings page can show what a switch means."""
    now = now or datetime.now(UTC)
    out: dict[str, int] = {}
    async with get_session_factory()() as session:
        for table in RETENTION_TABLES:
            cutoff = await _cutoff(table, now)
            if table == "checkpoints":
                out[table] = await _checkpoint_thread_sql(session, "COUNT", cutoff)
                continue
            stmt = _eligible(table, cutoff)
            out[table] = int(
                (
                    await session.execute(select(func.count()).select_from(stmt.subquery()))
                ).scalar_one()
            )
    return out


async def _purge_by_id(table: str, cutoff: datetime) -> int:
    """The common shape: select eligible ids, delete them, batch by batch."""
    model = _MODELS[table]
    deleted = 0
    while True:
        async with get_session_factory()() as session:
            ids = list((await session.execute(_eligible(table, cutoff).limit(_BATCH))).scalars())
            if not ids:
                break
            await session.execute(delete(model).where(model.id.in_(ids)))
            await session.commit()
        deleted += len(ids)
        if len(ids) < _BATCH:
            break
        await asyncio.sleep(0)  # yield between batches — a big purge never owns the loop
    return deleted


async def _trimmable_run_ids(session: Any, cutoff: datetime, limit: int) -> list[Any]:
    return list(
        (
            await session.execute(select(Run.id).where(_trimmable_runs(cutoff)).limit(limit))
        ).scalars()
    )


async def _purge_run_steps(cutoff: datetime) -> int:
    """Trim the trace, keep the run. Batched BY RUN, never by step id:
    `run_steps.parent_step_id` points at another step of the same run, so a
    batch that split a run between two statements would fail its own foreign
    key. Returns the number of STEP rows removed."""
    deleted = 0
    while True:
        async with get_session_factory()() as session:
            # the runs that STILL have steps, so the batch shrinks as it works
            run_ids = list(
                (
                    await session.execute(
                        select(RunStep.run_id)
                        .distinct()
                        .where(RunStep.run_id.in_(select(Run.id).where(_trimmable_runs(cutoff))))
                        .limit(_RUN_BATCH)
                    )
                ).scalars()
            )
            if not run_ids:
                break
            removed = int(
                (
                    await session.execute(
                        select(func.count()).select_from(RunStep).where(RunStep.run_id.in_(run_ids))
                    )
                ).scalar_one()
            )
            await session.execute(delete(RunStep).where(RunStep.run_id.in_(run_ids)))
            await session.commit()
        deleted += removed
        if len(run_ids) < _RUN_BATCH:
            break
        await asyncio.sleep(0)
    return deleted


async def _purge_runs(cutoff: datetime) -> int:
    """Remove the run and everything that hangs off it — its steps and its
    checkpoints — in one statement each, per batch of runs. Spec §8.7: a
    purged run leaves NO residue, so the checkpoint rows go with it whatever
    the checkpoint gate says; that gate governs trimming checkpoints out from
    under runs that stay, not orphaning rows behind ones that go. Returns the
    number of RUN rows removed."""
    deleted = 0
    while True:
        async with get_session_factory()() as session:
            run_ids = await _trimmable_run_ids(session, cutoff, _RUN_BATCH)
            if not run_ids:
                break
            threads = {str(r) for r in run_ids}
            for table in CHECKPOINT_TABLES:
                exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": table})
                if exists.scalar_one_or_none() is None:
                    continue
                await session.execute(
                    text(
                        f"DELETE FROM {table} "  # noqa: S608 - fixed table names
                        "WHERE split_part(thread_id, ':', 1) = ANY(CAST(:threads AS text[]))"
                    ),
                    {"threads": sorted(threads)},
                )
            await session.execute(delete(RunStep).where(RunStep.run_id.in_(run_ids)))
            await session.execute(delete(Run).where(Run.id.in_(run_ids)))
            await session.commit()
        deleted += len(run_ids)
        if len(run_ids) < _RUN_BATCH:
            break
        await asyncio.sleep(0)
    return deleted


async def purge_table(table: str, now: datetime | None = None) -> int:
    """Delete the eligible rows of one table, in batches. THE GATE IS CHECKED
    HERE (M48 §3.7.1): a purge behind an off switch returns 0 whoever calls it."""
    if table not in RETENTION_TABLES:
        raise KeyError(f"unknown retention table {table!r}")
    if not await gate_open(table):
        return 0
    now = now or datetime.now(UTC)
    cutoff = await _cutoff(table, now)
    deleted = 0
    if table == "checkpoints":
        async with get_session_factory()() as session:
            deleted = await _checkpoint_thread_sql(session, "DELETE", cutoff)
            await session.commit()
    elif table == "runs":
        deleted = await _purge_runs(cutoff)
    elif table == "run_steps":
        deleted = await _purge_run_steps(cutoff)
    else:
        deleted = await _purge_by_id(table, cutoff)
    if deleted:
        obs.RETENTION_DELETED.labels(table=table).inc(deleted)
        logger.info("retention_purged", table=table, deleted=deleted, cutoff=cutoff.isoformat())
    return deleted


async def run_retention(now: datetime | None = None) -> dict[str, int]:
    """One pass over every table under the advisory lock. Returns the
    per-table delete counts, or {} when another replica holds the lock."""
    async with get_session_factory()() as session:
        held = (
            await session.execute(
                text("SELECT pg_try_advisory_lock(:c, :o)"),
                {"c": RETENTION_LOCK_CLASSID, "o": RETENTION_LOCK_OBJID},
            )
        ).scalar()
        if not held:
            logger.info("retention_skipped", reason="lock held by another replica")
            return {}
        try:
            results: dict[str, int] = {}
            for table in RETENTION_TABLES:
                try:
                    results[table] = await purge_table(table, now)
                except Exception as exc:  # noqa: BLE001 — one table's failure never blocks the others
                    obs.LOOP_ERRORS.labels(loop="retention").inc()
                    logger.warning("retention_table_failed", table=table, error=str(exc)[:200])
                    results[table] = 0
            return results
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:c, :o)"),
                {"c": RETENTION_LOCK_CLASSID, "o": RETENTION_LOCK_OBJID},
            )


async def maybe_run_retention() -> dict[str, int] | None:
    """Periodic-loop hook: run once per RETENTION_INTERVAL_S (first tick
    included — the gates decide whether anything is deleted). M54: the
    clock is `job_clock`, so the interval holds across the fleet."""
    from app.jobclock import job_due, job_ran

    if not await job_due("retention", RETENTION_INTERVAL_S):
        return None
    result = await run_retention()
    await job_ran("retention")
    return result


def reset_retention_clock() -> None:
    """Testing hook — the clock is `job_clock` since M54 (truncated between
    tests); kept for the suites that call it."""
    global _LAST_RUN
    _LAST_RUN = None
