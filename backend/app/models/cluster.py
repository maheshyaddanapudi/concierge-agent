"""Cluster tables (M54, spec §18.9): replica liveness, the persisted job
clock and the distributed rate limiter's buckets. Three small tables that
turn per-process state into cluster state — no broker, Postgres only."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
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
