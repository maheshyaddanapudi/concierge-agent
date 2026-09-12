"""The persisted job clock (M54, arch-C3): `last_run_at` per periodic job in
`job_clock`, so an interval is a property of the cluster rather than of a
process's monotonic clock. Advisory locks keep guarding *concurrency* (two
replicas never run one job at once); this table guards *scheduling* (the
job runs once per interval, and a restarted replica re-runs nothing)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_session_factory
from app.models.cluster import JobClock


async def last_run(job: str) -> datetime | None:
    async with get_session_factory()() as session:
        value = await session.scalar(select(JobClock.last_run_at).where(JobClock.job == job))
    return value if isinstance(value, datetime) else None


async def job_due(job: str, interval_s: float, now: datetime | None = None) -> bool:
    """Due when it never ran, or when the interval has elapsed since it did."""
    now = now or datetime.now(UTC)
    last = await last_run(job)
    if last is None:
        return True
    return now - last >= timedelta(seconds=interval_s)


async def job_ran(job: str, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    async with get_session_factory()() as session:
        stmt = pg_insert(JobClock).values(job=job, last_run_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[JobClock.job], set_={"last_run_at": stmt.excluded.last_run_at}
        )
        await session.execute(stmt)
        await session.commit()
