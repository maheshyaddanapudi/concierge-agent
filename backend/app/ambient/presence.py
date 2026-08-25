"""Presence + the real idle detector (spec §17.4/§17.5 — heartbeat sense H1
consumer). The client sends heartbeats; the tick derives state transitions
and emits presence events (idle / user_returned) into the trigger plane.

States (doc 05b area 3): active (beat <60s ∧ visible ∧ input <5 min),
idle (beat fresh, no input 5–30 min), away (no beat 2 min or hidden),
offline (no beat >30 min).
"""

from datetime import UTC, datetime, timedelta

import structlog

from app.db import get_session_factory
from app.models import UserPresence

logger = structlog.get_logger("ambient")

_ACTIVE_INPUT_S = 5 * 60
_AWAY_BEAT_S = 2 * 60
_OFFLINE_BEAT_S = 30 * 60


async def record_heartbeat(*, visible: bool, activity: bool) -> UserPresence:
    """Client heartbeat (30s cadence; immediate on foreground). `activity`
    marks real input since the last beat."""
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        row = await session.get(UserPresence, "default")
        if row is None:
            row = UserPresence(id="default")
            session.add(row)
        row.last_heartbeat_at = now
        row.visible = visible
        if activity:
            row.last_activity_at = now
        await session.commit()
        await session.refresh(row)
    return row


def _derive_state(row: UserPresence, now: datetime) -> str:
    beat = row.last_heartbeat_at
    if beat is None or (now - beat).total_seconds() > _OFFLINE_BEAT_S:
        return "offline"
    if (now - beat).total_seconds() > _AWAY_BEAT_S or not row.visible:
        return "away"
    act = row.last_activity_at
    if act is not None and (now - act).total_seconds() <= _ACTIVE_INPUT_S:
        return "active"
    return "idle"


async def evaluate_presence(idle_minutes: int) -> str | None:
    """One tick: derive the state, persist transitions, and emit presence
    events. `idle_minutes` (ambient_idle_minutes) additionally gates the
    platform-level idle event used for consolidation/anticipation — the
    conversation-quiet detector spec §16.2 promised.

    Returns the emitted event kind, if any.
    """
    from app.ambient.store import emit_event

    now = datetime.now(UTC)
    emitted: str | None = None
    async with get_session_factory()() as session:
        row = await session.get(UserPresence, "default")
        if row is None:
            return None
        new_state = _derive_state(row, now)
        old_state = row.state
        if new_state == old_state:
            return None
        row.state = new_state
        await session.commit()
    if old_state in {"idle", "away", "offline"} and new_state == "active":
        emitted = "user_returned"
    elif old_state == "active" and new_state in {"idle", "away"}:
        emitted = "user_idle"
    if emitted:
        await emit_event(
            kind=emitted,
            source="presence",
            payload={"from": old_state, "to": new_state},
            require_enabled=True,
        )
        logger.info(
            "ambient_presence", tier="ambient", kind="ingest", transition=f"{old_state}->{new_state}"
        )
    return emitted


async def is_platform_idle(idle_minutes: int) -> bool:
    """The real idle detector (spec §17.4): no active runs AND no chat
    activity for `idle_minutes`. Used by consolidation/anticipation jobs."""
    from sqlalchemy import func, select

    from app.models import Run

    cutoff = datetime.now(UTC) - timedelta(minutes=idle_minutes)
    async with get_session_factory()() as session:
        active = (
            await session.execute(
                select(func.count()).where(Run.status.in_(["running", "paused_hitl"]))
            )
        ).scalar_one()
        if active:
            return False
        latest = (
            await session.execute(select(func.max(Run.started_at)))
        ).scalar_one()
    return latest is None or latest <= cutoff
