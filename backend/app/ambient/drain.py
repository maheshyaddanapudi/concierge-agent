"""The ambient drain (spec §17.2): NOTIFY wakes it, the table is the truth.

Pending events are claimed with FOR UPDATE SKIP LOCKED and handed to the
registered processor. M20 ships the substrate: the default processor leaves
events pending (the decision plane lands in M21) — the drain's job here is
liveness, ordering, and the wake path. The loop is lifespan-owned and a
no-op while `ambient_enabled` is false (byte-identity when dark).
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from sqlalchemy import text as sql_text

from app.ambient.store import NOTIFY_CHANNEL
from app.db import get_session_factory
from app.models import AmbientEvent

logger = structlog.get_logger("ambient")

# processor contract: return (verdict, reason) or None to leave pending
Processor = Callable[[AmbientEvent], Awaitable[tuple[str, str] | None]]
_processor: Processor | None = None


def register_processor(fn: Processor | None) -> None:
    """The loop installs the decision plane here; tests install fakes."""
    global _processor
    _processor = fn


async def default_processor(event: AmbientEvent) -> tuple[str, str] | None:
    """M21 decision plane: patterns advance first (derived events), then the
    three-tier gate decides fire/hold for this event."""
    from app.ambient.decide import process_event
    from app.ambient.patterns import advance_patterns

    await advance_patterns(event)
    return await process_event(event)


async def drain_once(limit: int = 20) -> int:
    """Claim and process pending events. Returns events handled."""
    handled = 0
    async with get_session_factory()() as session:
        rows = (
            (
                await session.execute(
                    sql_text(
                        """
                        SELECT id FROM ambient_events
                        WHERE verdict IS NULL
                        ORDER BY received_at
                        LIMIT :n
                        FOR UPDATE SKIP LOCKED
                        """
                    ),
                    {"n": limit},
                )
            )
            .scalars()
            .all()
        )
        for event_id in rows:
            event = await session.get(AmbientEvent, event_id)
            if event is None:
                continue
            outcome: tuple[str, str] | None = None
            if _processor is not None:
                try:
                    outcome = await _processor(event)
                except Exception as exc:  # noqa: BLE001 — the drain never dies
                    outcome = ("held", f"processor error: {exc}")
            if outcome is not None:
                verdict, reason = outcome
                event.verdict = verdict
                event.verdict_reason = reason
                event.processed_at = datetime.now(UTC)
                handled += 1
        await session.commit()
    if handled:
        from app import obs

        obs.AMBIENT_OPS.labels(kind="drain", status="ok").inc()
        logger.info("ambient_drain", tier="ambient", kind="drain", handled=handled)
    return handled


async def run_ambient_loop(stop: asyncio.Event, tick_s: float = 60.0) -> None:
    """Lifespan-owned loop: LISTEN for wake pings, sweep on the tick.
    Cheap no-op while ambient is dark."""
    from app.registry_cache import get_cache

    wake = asyncio.Event()
    listener_task: asyncio.Task[None] | None = None

    async def _listen() -> None:
        # dedicated (unpooled) connection: LISTEN breaks under pooling
        import asyncpg  # type: ignore[import-untyped]

        from app.config import get_config

        dsn = get_config().database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            await conn.add_listener(NOTIFY_CHANNEL, lambda *_: wake.set())
            await stop.wait()
        finally:
            await conn.close()

    while not stop.is_set():
        try:
            enabled = bool(await get_cache().setting("ambient_enabled"))
            if enabled:
                if listener_task is None or listener_task.done():
                    listener_task = asyncio.create_task(_listen())
                if _processor is None:
                    register_processor(default_processor)
                # trigger evaluators (spec §17.2) then the drain
                from app.ambient.decide import sweep_hitl_aging
                from app.ambient.patterns import expire_pattern_deadlines
                from app.ambient.triggers import (
                    evaluate_schedules,
                    evaluate_state_conditions,
                    poll_due_intents,
                )

                await evaluate_schedules()
                await poll_due_intents()
                await evaluate_state_conditions()
                await expire_pattern_deadlines()
                await sweep_hitl_aging()
                await drain_once()
                idle_minutes = int(await get_cache().setting("ambient_idle_minutes"))
                from app.ambient.presence import evaluate_presence

                await evaluate_presence(idle_minutes)
        except Exception as exc:  # noqa: BLE001 — the loop must survive anything
            logger.warning("ambient_tick_failed", error=str(exc))
        wake.clear()
        waiters = {asyncio.create_task(stop.wait()), asyncio.create_task(wake.wait())}
        _, pending = await asyncio.wait(
            waiters, timeout=tick_s, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    if listener_task is not None:
        listener_task.cancel()
