"""Per-run execution context, carried by contextvar through every coroutine
the run spawns (orchestrator nodes, middlewares, tools, workers)."""

import asyncio
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


class RunEventBus:
    """In-memory SSE fan-out per run: history replay + live queues."""

    def __init__(self) -> None:
        self._runs: dict[UUID, dict[str, Any]] = {}

    def _entry(self, run_id: UUID) -> dict[str, Any]:
        return self._runs.setdefault(run_id, {"history": [], "queues": set(), "done": False})

    def emit(self, run_id: UUID, event: dict[str, Any]) -> None:
        entry = self._entry(run_id)
        entry["history"].append(event)
        if event.get("type") == "done" or (
            event.get("type") == "run_status"
            and event.get("payload", {}).get("status") in {"failed", "cancelled", "completed"}
        ):
            entry["done"] = True
        for queue in list(entry["queues"]):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    def is_done(self, run_id: UUID) -> bool:
        return bool(self._entry(run_id)["done"])

    def subscribe(self, run_id: UUID) -> tuple[list[dict[str, Any]], asyncio.Queue[Any]]:
        entry = self._entry(run_id)
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1000)
        entry["queues"].add(queue)
        return list(entry["history"]), queue

    def unsubscribe(self, run_id: UUID, queue: asyncio.Queue[Any]) -> None:
        self._entry(run_id)["queues"].discard(queue)

    def forget(self, run_id: UUID) -> None:
        self._runs.pop(run_id, None)


EVENT_BUS = RunEventBus()


@dataclass
class RunFlags:
    """Mutable per-run switches (e.g. the agentic use_full_catalog escalation)."""

    full_catalog: bool = False


@dataclass
class RunContext:
    run_id: UUID
    mode: str
    recorder: Any  # RunRecorder — Any avoids a circular import
    flags: RunFlags = field(default_factory=RunFlags)
    settings: dict[str, Any] = field(default_factory=dict)
    callbacks: list[Any] = field(default_factory=list)


_CURRENT: ContextVar[RunContext | None] = ContextVar("run_context", default=None)


def set_run_context(ctx: RunContext) -> None:
    _CURRENT.set(ctx)


def get_run_context() -> RunContext | None:
    return _CURRENT.get()


def require_run_context() -> RunContext:
    ctx = _CURRENT.get()
    if ctx is None:
        raise RuntimeError("no active run context")
    return ctx
