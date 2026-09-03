"""The distributed rate limiter (M54, scale-H3): the §18.8 token bucket kept
in `rate_buckets`, so N replicas grant one budget instead of N. One short
transaction per request (a locked read, an upsert); keys idle for an hour
are evicted by the periodic loop, so the key space — user ids, or client
addresses an attacker controls — stays bounded. A database failure fails
OPEN with a log: availability over a limit the pool itself already bounds
(M51 admission)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_session_factory
from app.models.cluster import RateBucket

logger = structlog.get_logger("ratelimit")

IDLE_EVICT_S = 3600.0


async def allow(key: str, burst: float, per_s: float, now: datetime | None = None) -> bool:
    """Refill by elapsed time, spend one token if there is one. True = allowed."""
    now = now or datetime.now(UTC)
    key = key[:128]
    async with get_session_factory()() as session:
        row = (
            await session.execute(
                text("SELECT tokens, ts FROM rate_buckets WHERE key = :key FOR UPDATE"),
                {"key": key},
            )
        ).first()
        if row is None:
            tokens = float(burst)
        else:
            elapsed = max((now - row.ts).total_seconds(), 0.0)
            tokens = min(float(burst), float(row.tokens) + elapsed * per_s)
        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0
        stmt = pg_insert(RateBucket).values(key=key, tokens=tokens, ts=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RateBucket.key],
            set_={"tokens": stmt.excluded.tokens, "ts": stmt.excluded.ts},
        )
        await session.execute(stmt)
        await session.commit()
    return allowed


async def evict_idle(idle_s: float = IDLE_EVICT_S, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    async with get_session_factory()() as session:
        result = await session.execute(
            delete(RateBucket).where(RateBucket.ts < now - timedelta(seconds=idle_s))
        )
        await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
