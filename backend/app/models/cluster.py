"""Cluster tables (M54, spec §18.9): replica liveness, the persisted job
clock and the distributed rate limiter's buckets. Three small tables that
turn per-process state into cluster state — no broker, Postgres only."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Replica(Base):
    """One row per live process, refreshed every REPLICA_HEARTBEAT_S. A row
    whose heartbeat is older than REPLICA_DEAD_AFTER_S is a dead replica:
    its runs are reaped, its subscriber count stops counting."""

    __tablename__ = "replicas"

    replica_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    subscribers: Mapped[int] = mapped_column(Integer, default=0)
    runs_in_flight: Mapped[int] = mapped_column(Integer, default=0)


class JobClock(Base):
    """`last_run_at` per periodic job — the interval becomes a cluster
    property (arch-C3): whichever replica leads a job, it runs once per
    interval, and a restart re-runs nothing."""

    __tablename__ = "job_clock"

    job: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RateBucket(Base):
    """The §18.8 token bucket, shared by every replica (scale-H3). Keys idle
    past an hour are evicted by the periodic loop — bounded key space."""

    __tablename__ = "rate_buckets"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobUsage(Base):
    """Model usage by work that is NOT a run (spec §3.7 cost model).

    The spend ceiling counted runs only, so every autonomous model call sat
    outside it: the overlap judge, the significance and salience judges,
    anticipation, run digests, reflection, community summaries, extraction
    and every embedding. The Settings hint said the ceiling was "one number
    for the whole deployment", and the dashboard reported $0 for all of it —
    so an operator at their ceiling watched chat refused while the
    background jobs kept billing, with nowhere to see where the money went.

    One row per out-of-run model call, priced at the moment it happened
    exactly as a run is: `spend_today` sums these alongside the runs.
    """

    __tablename__ = "job_usage"
    __table_args__ = (Index("job_usage_at_idx", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # the job class that spent it: overlap_audit, significance, salience,
    # anticipation, digest, reflection, community, extraction, eval_judge,
    # embedding, watch_compile, …
    kind: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(255), default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=None)
    # false when the model has no price anywhere — reported, never guessed
    cost_priced: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
