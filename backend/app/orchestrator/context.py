"""Per-run execution context, carried by contextvar through every coroutine
the run spawns (orchestrator nodes, middlewares, tools, workers)."""

import asyncio
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


class RunEventBus:
    """In-memory SSE fan-out per run: history replay + live queues.

    M51: bounded. Finished runs are evicted after `done_ttl_s` and the map
    never holds more than `max_runs` entries (oldest finished go first);
    read paths (`is_done`) allocate nothing. Before M51 every run ever
    emitted lived here until purge — the arch-H review's unbounded growth."""

    def __init__(self, max_runs: int = 500, done_ttl_s: float = 900.0) -> None:
        self._runs: dict[UUID, dict[str, Any]] = {}
        self.max_runs = max_runs
        self.done_ttl_s = done_ttl_s

    def _entry(self, run_id: UUID) -> dict[str, Any]:
        return self._runs.setdefault(
            run_id, {"history": [], "queues": set(), "done": False, "done_at": None, "seq": 0}
        )

    @staticmethod
    def _now() -> float:
        import time

        return time.monotonic()

    def _evict(self, now: float) -> None:
        expired = [
            rid
            for rid, e in self._runs.items()
            if e["done"] and e["done_at"] is not None and now - e["done_at"] >= self.done_ttl_s
        ]
        for rid in expired:
            self._runs.pop(rid, None)
        if len(self._runs) > self.max_runs:
            finished = sorted(
                (rid for rid, e in self._runs.items() if e["done"]),
                key=lambda rid: self._runs[rid]["done_at"] or 0.0,
            )
            for rid in finished[: len(self._runs) - self.max_runs]:
                self._runs.pop(rid, None)

    def emit(self, run_id: UUID, event: dict[str, Any], now: float | None = None) -> None:
        now = self._now() if now is None else now
        entry = self._entry(run_id)
        # M53: a monotonic per-run sequence is the SSE `id:` — a reconnecting
        # client resumes from it, and never folds the same event twice
        entry["seq"] += 1
        event["seq"] = entry["seq"]
        entry["history"].append(event)
        if event.get("type") == "done" or (
            event.get("type") == "run_status"
            and event.get("payload", {}).get("status") in {"failed", "cancelled", "completed"}
        ):
            entry["done"] = True
            entry["done_at"] = now
        for queue in list(entry["queues"]):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)
        self._evict(now)

    def is_done(self, run_id: UUID) -> bool:
        entry = self._runs.get(run_id)
        return bool(entry and entry["done"])

    def last_seq(self, run_id: UUID) -> int:
        entry = self._runs.get(run_id)
        return int(entry["seq"]) if entry else 0

    def subscribe(
        self, run_id: UUID, after: int = 0
    ) -> tuple[list[dict[str, Any]], asyncio.Queue[Any]]:
        """History after sequence `after` (0 = everything) plus a live queue."""
        from app import obs

        entry = self._entry(run_id)
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1000)
        entry["queues"].add(queue)
        obs.SSE_SUBSCRIBERS.labels(stream="chat").inc()
        return [e for e in entry["history"] if int(e.get("seq", 0)) > after], queue

    def unsubscribe(self, run_id: UUID, queue: asyncio.Queue[Any]) -> None:
        from app import obs

        queues = self._entry(run_id)["queues"]
        if queue in queues:
            queues.discard(queue)
            obs.SSE_SUBSCRIBERS.labels(stream="chat").dec()

    def forget(self, run_id: UUID) -> None:
        self._runs.pop(run_id, None)


EVENT_BUS = RunEventBus()


@dataclass
class RunFlags:
    """Mutable per-run switches (e.g. the agentic use_full_catalog escalation)."""

    full_catalog: bool = False


# ephemeral worker callsigns (spec §7.1 rung 4): sequential per run, so
# parallel dynamic workers stay distinguishable in rails, ticker, and trace
WORKER_CALLSIGNS = (
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliett",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "xray",
    "yankee",
    "zulu",
)


@dataclass
class RunContext:
    run_id: UUID
    mode: str
    recorder: Any  # RunRecorder — Any avoids a circular import
    conversation_id: UUID | None = None  # provenance for memory writes (spec §16)
    flags: RunFlags = field(default_factory=RunFlags)
    settings: dict[str, Any] = field(default_factory=dict)
    callbacks: list[Any] = field(default_factory=list)
    worker_count: int = 0
    # retrieval (spec §7.4): the ranking query + ids pinned past ranking
    query_text: str = ""
    pinned_ids: set[str] = field(default_factory=set)
    # §16.5: exemplars injected into this run's planner (vote lifecycle)
    used_exemplar_ids: list[Any] = field(default_factory=list)
    # §16.7: memory ids injected into any surface this run (citation feedback)
    injected_memory_ids: list[str] = field(default_factory=list)
    # §17.4: the owning routine's narrowed registry projection — None for
    # interactive runs and for routines without an allowlist
    ambient_allowlist: dict[str, Any] | None = None
    # §18.1: the routine's model_ref — replaces the default_model FALLBACK
    # everywhere this run resolves a model; explicit role/skill models win
    ambient_model_ref: str | None = None

    def next_worker_callsign(self) -> str:
        n = self.worker_count
        self.worker_count += 1
        name = WORKER_CALLSIGNS[n % len(WORKER_CALLSIGNS)]
        suffix = n // len(WORKER_CALLSIGNS)
        return f"worker-{name}" if suffix == 0 else f"worker-{name}-{suffix + 1}"


def ambient_default_override() -> str | None:
    """The current run's ambient model override, if any (§18.1)."""
    ctx = get_run_context()
    return ctx.ambient_model_ref if ctx is not None else None


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
