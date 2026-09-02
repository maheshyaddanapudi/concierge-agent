"""Run admission control (M51, PLAN M51 — "nothing bounds admission").

The M49 baseline showed 50 concurrent runs all completing while end-to-end
latency grew linearly: every POST /chat became a task immediately and they
all contended for the same pool, the same event loop, and the same
provider budget. Admission is now explicit and truthful:

- at most `run_max_concurrent` runs execute at once (a semaphore);
- up to `run_queue_max` more wait in `status='queued'` — visible, not
  invented;
- past that, callers that asked to be shed (chat) get an explicit 503 with
  Retry-After instead of an invisible wait; ambient fires queue regardless,
  because a fire is work the system already accepted.

`set_accepting(False)` is the readiness gate: a draining process refuses
new work (503) while in-flight runs finish or are cancelled (M51 shutdown).
The counters are process-local, like RUNNING_TASKS — M54 moves the run
registry to Postgres; this is the per-replica half it will keep.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID


class AtCapacity(RuntimeError):
    """The queue is full (or the process is draining) — shed the request."""

    def __init__(self, detail: str, retry_after_s: int = 5) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retry_after_s = retry_after_s


_running: set[UUID] = set()
_queued: set[UUID] = set()
_accepting = True
_semaphore: asyncio.Semaphore | None = None
_semaphore_size = 0


def reset() -> None:
    """Testing hook: forget counters and the cached semaphore."""
    global _semaphore, _semaphore_size, _accepting
    _running.clear()
    _queued.clear()
    _semaphore = None
    _semaphore_size = 0
    _accepting = True


def set_accepting(value: bool) -> None:
    global _accepting
    _accepting = value


def accepting() -> bool:
    return _accepting


def snapshot() -> dict[str, Any]:
    return {
        "accepting": _accepting,
        "running": len(_running),
        "queued": len(_queued),
        "max_concurrent": _semaphore_size,
    }


def _limits_from(settings: dict[str, Any]) -> tuple[int, int]:
    return (
        max(int(settings.get("run_max_concurrent") or 8), 1),
        max(int(settings.get("run_queue_max") or 0), 0),
    )


def _get_semaphore(max_concurrent: int) -> asyncio.Semaphore:
    """One semaphore per process; a changed setting rebuilds it when idle
    (rebuilding mid-flight would orphan holders)."""
    global _semaphore, _semaphore_size
    if _semaphore is None or (_semaphore_size != max_concurrent and not _running):
        _semaphore = asyncio.Semaphore(max_concurrent)
        _semaphore_size = max_concurrent
    return _semaphore


def check_admission(settings: dict[str, Any], *, shed_if_full: bool) -> None:
    """Synchronous gate at run creation. Raises AtCapacity when the caller
    asked to be shed and the queue is full, or whenever the process is
    not accepting work (draining)."""
    if not _accepting:
        raise AtCapacity("not accepting new runs: this replica is draining", retry_after_s=10)
    if not shed_if_full:
        return
    max_concurrent, queue_max = _limits_from(settings)
    if len(_running) >= max_concurrent and len(_queued) >= queue_max:
        raise AtCapacity(
            f"server at capacity: {len(_running)} running, {len(_queued)} queued "
            f"(run_max_concurrent={max_concurrent}, run_queue_max={queue_max}) — retry later"
        )


@asynccontextmanager
async def slot(run_id: UUID, settings: dict[str, Any]) -> AsyncIterator[None]:
    """Wait for an execution slot (the run is `queued` meanwhile), hold it
    for the body, release on any exit."""
    max_concurrent, _ = _limits_from(settings)
    sem = _get_semaphore(max_concurrent)
    _queued.add(run_id)
    try:
        await sem.acquire()
    except BaseException:
        _queued.discard(run_id)
        raise
    _queued.discard(run_id)
    _running.add(run_id)
    try:
        yield
    finally:
        _running.discard(run_id)
        sem.release()
