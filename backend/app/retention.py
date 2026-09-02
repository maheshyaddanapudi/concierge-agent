"""Retention for the six unbounded tables (M53, arch-M6).

`ambient_events`, `deliveries`, `ambient_policies`, `pattern_instances`,
`a2a_tasks` and `auth_sessions` had no retention job, no TTL and no purge
surface: at a year of operation the two ambient ledgers dominate the
database and slow every tick, and the only way to trim them was manual SQL.

Each table now has a purge with its own window and — per the §3.7.1
discipline M48 established — its own gate, ENFORCED INSIDE THE PURGE
FUNCTION, so no call path (the hourly tick, the operator's "run now", a
test) deletes anything behind a switch that is off. Every purge deletes only
rows the system is finished with: processed events, delivered or superseded
deliveries, superseded policy rows (the latest row per category is the live
policy and is never touched), matched or expired pattern instances,
terminal A2A tasks, and sessions past their expiry. Pending, armed, open and
current rows survive whatever their age.

Deleting is destructive, so five of the six gates are born dark; only the
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
from sqlalchemy import Select, delete, func, select, text

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
)

logger = structlog.get_logger("retention")

RETENTION_TABLES: tuple[str, ...] = (
    "ambient_events",
    "deliveries",
    "ambient_policies",
    "pattern_instances",
    "a2a_tasks",
    "auth_sessions",
)
RETENTION_GATES: dict[str, str] = {t: f"retention_{t}_enabled" for t in RETENTION_TABLES}
RETENTION_WINDOWS: dict[str, str] = {t: f"retention_{t}_days" for t in RETENTION_TABLES}

# a dedicated advisory-lock pair: never the memory jobs' classid (42016) nor
# the ambient leader's (427017) — part of the cross-replica contract
RETENTION_LOCK_CLASSID = 427018
RETENTION_LOCK_OBJID = 1

RETENTION_INTERVAL_S = 3600.0
_BATCH = 5000
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
    raise KeyError(f"unknown retention table {table!r}")


_MODELS: dict[str, Any] = {
    "ambient_events": AmbientEvent,
    "deliveries": Delivery,
    "ambient_policies": AmbientPolicy,
    "pattern_instances": PatternInstance,
    "a2a_tasks": A2ATask,
    "auth_sessions": AuthSession,
}


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
            stmt = _eligible(table, await _cutoff(table, now))
            out[table] = int(
                (
                    await session.execute(select(func.count()).select_from(stmt.subquery()))
                ).scalar_one()
            )
    return out


async def purge_table(table: str, now: datetime | None = None) -> int:
    """Delete the eligible rows of one table, in batches. THE GATE IS CHECKED
    HERE (M48 §3.7.1): a purge behind an off switch returns 0 whoever calls it."""
    if table not in _MODELS:
        raise KeyError(f"unknown retention table {table!r}")
    if not await gate_open(table):
        return 0
    now = now or datetime.now(UTC)
    cutoff = await _cutoff(table, now)
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
    included — the gates decide whether anything is deleted)."""
    global _LAST_RUN
    now = asyncio.get_event_loop().time()
    if _LAST_RUN is not None and now - _LAST_RUN < RETENTION_INTERVAL_S:
        return None
    _LAST_RUN = now
    return await run_retention()


def reset_retention_clock() -> None:
    """Testing hook."""
    global _LAST_RUN
    _LAST_RUN = None
