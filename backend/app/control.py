"""The control channel (M54, spec §18.9): one LISTEN/NOTIFY channel every
replica listens on, carrying the three cluster-wide facts the process-local
design had no way to share — a cancel intent for a run executing elsewhere,
a terminal transition a stream held elsewhere is waiting for, and an in-app
delivery every replica must re-fan to its own subscribers. No broker (§2):
`pg_notify` carries the message, the row it names is the truth, and every
consumer has a fallback that re-reads the row (the heartbeat, the stream's
beat), so a lost notification costs latency, never correctness.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text

from app.db import get_session_factory
from app.replica import replica_id

logger = structlog.get_logger("control")

CONTROL_CHANNEL = "concierge_control"
_PAYLOAD_LIMIT = 7000  # pg_notify caps a payload at 8000 bytes

_terminal_waiters: dict[UUID, set[asyncio.Event]] = {}
_tasks: set[asyncio.Task[Any]] = set()
_listener: Any = None


async def notify(kind: str, **fields: Any) -> None:
    """Announce on the channel. Best-effort by design — every consumer has
    a row-reading fallback — so a failure is logged, never raised."""
    message = {"kind": kind, "origin": replica_id(), **fields}
    payload = json.dumps(message, default=str)
    if len(payload.encode()) > _PAYLOAD_LIMIT and "title" in message:
        message["title"] = str(message["title"])[:200]
        payload = json.dumps(message, default=str)
    try:
        async with get_session_factory()() as session:
            await session.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CONTROL_CHANNEL, "payload": payload},
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — the row is the truth; the notify is the fast path
        logger.warning("control_notify_failed", kind=kind, error=str(exc)[:200])


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def dispatch(payload: str) -> None:
    """The listener callback (sync): route one message by kind."""
    try:
        message = json.loads(payload)
    except (TypeError, ValueError):
        logger.warning("control_bad_payload", head=str(payload)[:80])
        return
    kind = str(message.get("kind") or "")
    origin = str(message.get("origin") or "")
    if kind == "cancel":
        from app.orchestrator import runner

        try:
            run_id = UUID(str(message.get("run_id")))
        except ValueError:
            return
        if run_id in runner.RUNNING_TASKS:
            _spawn(runner.cancel_local(run_id, reason=f"cancelled by request (from {origin})"))
    elif kind == "terminal":
        try:
            run_id = UUID(str(message.get("run_id")))
        except ValueError:
            return
        for event in list(_terminal_waiters.get(run_id, ())):
            event.set()
    elif kind == "delivery":
        if origin == replica_id():
            return  # our own toast already went to our own subscribers
        from app.ambient import channels

        channels.fan_in(message)


def watch_terminal(run_id: UUID) -> asyncio.Event:
    """An event set when the owner announces the run's terminal transition."""
    event = asyncio.Event()
    _terminal_waiters.setdefault(run_id, set()).add(event)
    return event


def unwatch_terminal(run_id: UUID, event: asyncio.Event) -> None:
    waiters = _terminal_waiters.get(run_id)
    if waiters is None:
        return
    waiters.discard(event)
    if not waiters:
        _terminal_waiters.pop(run_id, None)


async def start_listener(base_backoff_s: float = 1.0) -> bool:
    """One supervised LISTEN per process (M53 SupervisedListener)."""
    global _listener
    from app.listen import SupervisedListener

    if _listener is None:
        _listener = SupervisedListener(CONTROL_CHANNEL, dispatch, base_backoff_s=base_backoff_s)
    ok = bool(await _listener.start())
    logger.info("control_listener_started", channel=CONTROL_CHANNEL, connected=ok)
    return ok


async def stop_listener() -> None:
    global _listener
    listener, _listener = _listener, None
    if listener is not None:
        await listener.stop()
    for task in list(_tasks):
        task.cancel()
        with contextlib.suppress(BaseException):
            await task


def listener_connected() -> bool:
    return bool(_listener is not None and _listener.connected)
