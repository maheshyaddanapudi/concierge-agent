"""Replica identity and liveness (M54, spec §18.9, arch-C3 / scale-B1).

Every process has a `replica_id` and keeps one row in `replicas` fresh.
Everything that used to be a fact about "the process" — who owns a run,
how many people are watching the delivery stream, whether a run's owner is
still alive — becomes a fact about the fleet by reading this table. The
boot lock lives here too: N replicas booting together migrate and seed
once.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_session_factory
from app.models.cluster import Replica

logger = structlog.get_logger("replica")

REPLICA_HEARTBEAT_S = 10.0
REPLICA_DEAD_AFTER_S = 45.0
# the boot lock (migrations + seeds): its own classid, never shared with the
# ambient leader (427017), retention (427018) or the memory jobs (42016)
BOOT_LOCK_CLASSID = 427019
BOOT_LOCK_OBJID = 1

_ID: str | None = None


def replica_id() -> str:
    """`REPLICA_ID` env, else the container hostname, else a random id —
    stable for the life of the process."""
    global _ID
    if _ID is None:
        _ID = (os.environ.get("REPLICA_ID") or socket.gethostname() or uuid4().hex[:12])[:128]
    return _ID


def set_replica_id(value: str | None) -> None:
    """Testing hook: pin (or forget) this process's identity."""
    global _ID
    _ID = value


async def heartbeat_once(
    *, subscribers: int | None = None, runs_in_flight: int | None = None
) -> None:
    """Upsert this replica's row with what it is doing right now."""
    if subscribers is None:
        from app.ambient.channels import stream_subscriber_count

        subscribers = stream_subscriber_count()
    if runs_in_flight is None:
        from app.orchestrator.runner import RUNNING_TASKS

        runs_in_flight = len(RUNNING_TASKS)
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        stmt = pg_insert(Replica).values(
            replica_id=replica_id(),
            started_at=now,
            heartbeat_at=now,
            subscribers=subscribers,
            runs_in_flight=runs_in_flight,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Replica.replica_id],
            set_={
                "heartbeat_at": stmt.excluded.heartbeat_at,
                "subscribers": stmt.excluded.subscribers,
                "runs_in_flight": stmt.excluded.runs_in_flight,
            },
        )
        await session.execute(stmt)
        await session.commit()
    from app import obs

    obs.REPLICA_INFO.labels(replica=replica_id()).set(1.0)


async def live_replicas(now: datetime | None = None) -> list[Replica]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=REPLICA_DEAD_AFTER_S)
    async with get_session_factory()() as session:
        rows = list(
            (await session.execute(select(Replica).where(Replica.heartbeat_at >= cutoff))).scalars()
        )
    return rows


async def all_replicas() -> list[Replica]:
    async with get_session_factory()() as session:
        return list((await session.execute(select(Replica).order_by(Replica.started_at))).scalars())


async def live_replica_ids(now: datetime | None = None) -> set[str]:
    return {r.replica_id for r in await live_replicas(now)}


async def cluster_audience(local: int, now: datetime | None = None) -> int:
    """The §18.4 pursuit oracle across the fleet: this replica's subscribers
    (live, never its own possibly stale row) plus the fresh counts of every
    other live replica."""
    me = replica_id()
    others = sum(int(r.subscribers) for r in await live_replicas(now) if r.replica_id != me)
    return local + others


async def retire() -> None:
    """Shutdown: drop this replica's row so nobody counts a gone process."""
    with contextlib.suppress(Exception):
        async with get_session_factory()() as session:
            await session.execute(delete(Replica).where(Replica.replica_id == replica_id()))
            await session.commit()


async def run_replica_heartbeat_loop(stop: asyncio.Event) -> None:
    """Lifespan-owned: a heartbeat every REPLICA_HEARTBEAT_S, the row gone
    on the way out (retire). A dead process lapses on the cutoff instead."""
    from app import obs

    try:
        while not stop.is_set():
            try:
                await heartbeat_once()
            except Exception as exc:  # noqa: BLE001 — the heartbeat must survive anything
                obs.LOOP_ERRORS.labels(loop="replica").inc()
                logger.warning("replica_heartbeat_failed", error=str(exc)[:200])
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=REPLICA_HEARTBEAT_S)
    finally:
        await retire()


@contextlib.asynccontextmanager
async def boot_lock() -> AsyncIterator[None]:
    """A session advisory lock held for the duration of migrations and
    seeding, on a dedicated connection (a pooled one could be reused by
    the very statements it guards). Blocks until the previous booter is
    done — N replicas booting together apply the schema once."""
    import asyncpg  # type: ignore[import-untyped]

    from app.config import get_config

    dsn = get_config().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn: Any = await asyncpg.connect(
        dsn, server_settings={"application_name": f"concierge-boot:{replica_id()}"}
    )
    try:
        await conn.execute("SELECT pg_advisory_lock($1, $2)", BOOT_LOCK_CLASSID, BOOT_LOCK_OBJID)
        yield
    finally:
        with contextlib.suppress(Exception):
            await conn.execute(
                "SELECT pg_advisory_unlock($1, $2)", BOOT_LOCK_CLASSID, BOOT_LOCK_OBJID
            )
        with contextlib.suppress(Exception):
            await conn.close()
