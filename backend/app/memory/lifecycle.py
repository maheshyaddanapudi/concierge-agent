"""L4 consolidation jobs (spec §16.2) — decay, reflection, contradiction.

All jobs: advisory-locked (one replica works), fail-open, §16.6-labeled, and
never hold a DB transaction across an LLM call. The periodic loop lives in
run_periodic_loop(), started from the FastAPI lifespan; each job is also
directly awaitable for tests and the experiment harness.
"""

import asyncio
import math
from datetime import UTC, datetime
from typing import Literal

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import get_session_factory
from app.models import Memory

logger = structlog.get_logger("memory")

# job ids for pg_try_advisory_lock (classid fixed in scheduler)
JOB_DECAY = 1
JOB_REFLECT = 2
JOB_CONTRADICT = 3
JOB_MINE = 4
JOB_COMPACT = 5

# GA-style reflection trigger: summed importance of unreflected memories
REFLECTION_IMPORTANCE_TRIGGER = 150
_REFLECTION_WINDOW = 50
# decay rule (spec §16.2): expire active unpinned rows whose effective
# importance importance·2^(−Δt_access/half_life) drops below this floor
_DECAY_EFFECTIVE_FLOOR = 1.0

_INTERVALS_S = {
    JOB_DECAY: 6 * 3600,
    JOB_REFLECT: 3600,
    JOB_CONTRADICT: 24 * 3600,
    JOB_MINE: 12 * 3600,
    JOB_COMPACT: 6 * 3600,
}
_LAST_RUN: dict[int, float] = {}


async def decay_sweep() -> int:
    """MemoryBank-style access-recency decay; pinned rows immune. Returns the
    number of rows expired (archived, never deleted)."""
    now = datetime.now(UTC)
    expired = 0
    async with get_session_factory()() as session:
        from app.registry_cache import get_cache

        default_hl = float(await get_cache().setting("memory_half_life_days"))
        rows = list(
            (
                await session.execute(
                    select(Memory).where(Memory.status == "active", Memory.pinned.is_(False))
                )
            ).scalars()
        )
        for m in rows:
            half_life_days = float(m.half_life_days) if m.half_life_days else default_hl
            anchor = m.last_accessed_at or m.recorded_at
            age_days = max((now - anchor).total_seconds() / 86400.0, 0.0)
            effective = m.importance * math.exp(-math.log(2) / half_life_days * age_days)
            if effective < _DECAY_EFFECTIVE_FLOOR:
                m.status = "expired"
                m.valid_to = m.valid_to or now
                expired += 1
        if expired:
            await session.commit()
    from app import obs

    obs.MEMORY_OPS.labels(kind="decay", status="ok").inc()
    logger.info("memory_decay", tier="memory", kind="decay", expired=expired)
    return expired


class InferredInsight(BaseModel):
    text: str = Field(description="one higher-order insight, 8-300 chars")
    kind: Literal["fact", "preference", "instruction"]
    importance: int = Field(ge=1, le=10)
    evidence: list[int] = Field(description="numbers of the source memories used")


class ReflectionOutput(BaseModel):
    insights: list[InferredInsight] = Field(default_factory=list)


async def reflection() -> int:
    """Generative-Agents reflection: when summed importance of recent
    unreflected memories crosses the trigger, synthesize up to 3 `inferred`
    memories with explicit evidence citations. Inferred instructions
    quarantine (store rules). Returns insights written."""
    from app.registry_cache import get_cache

    cache = get_cache()
    if not await cache.setting("memory_reflection_enabled"):
        return 0
    async with get_session_factory()() as session:
        recent = list(
            (
                await session.execute(
                    select(Memory)
                    .where(Memory.status == "active", Memory.source != "inferred")
                    .order_by(Memory.recorded_at.desc())
                    .limit(_REFLECTION_WINDOW)
                )
            ).scalars()
        )
    # anti-repeat: only memories not already cited by an inferred row
    async with get_session_factory()() as session:
        inferred_rows = list(
            (await session.execute(select(Memory).where(Memory.source == "inferred"))).scalars()
        )
    cited: set[str] = set()
    for row in inferred_rows:
        cited.update((row.payload or {}).get("evidence", []))
    fresh = [m for m in recent if str(m.id) not in cited]
    if sum(m.importance for m in fresh) < REFLECTION_IMPORTANCE_TRIGGER:
        return 0
    try:
        from app.memory.extract import _extraction_model
        from app.prompts import load_prompt

        _, model = await _extraction_model()
        structured = model.with_structured_output(ReflectionOutput)  # type: ignore[attr-defined]
        listing = "\n".join(f"{i + 1}. [{m.kind}] {m.text}" for i, m in enumerate(fresh))
        out = await structured.ainvoke(load_prompt("memory_reflect").format(memories=listing))
        assert isinstance(out, ReflectionOutput)
    except Exception as exc:  # noqa: BLE001 — reflection is optional cognition
        logger.info("memory_reflection_failed", error=str(exc))
        return 0
    from app.memory.store import remember

    written = 0
    for insight in out.insights[:3]:
        evidence_ids = [str(fresh[i - 1].id) for i in insight.evidence if 1 <= i <= len(fresh)]
        if not evidence_ids:
            continue  # uncited insights are not auditable — refuse them
        try:
            await remember(
                text=insight.text,
                kind=insight.kind,
                source="inferred",
                importance=insight.importance,
                confidence=0.6,
                payload={"evidence": evidence_ids},
                run_id=fresh[0].run_id,  # provenance: newest evidence run
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory_reflection_write_failed", error=str(exc))
    from app import obs

    obs.MEMORY_OPS.labels(kind="reflect", status="ok").inc()
    logger.info("memory_reflection", tier="memory", kind="reflect", written=written)
    return written


async def contradiction_sweep() -> int:
    """Deterministic drift catcher: two ACTIVE rows sharing an entity_key
    should not coexist (supersession handles the normal path) — quarantine
    the newer of each pair for human review. Returns rows quarantined."""
    quarantined = 0
    async with get_session_factory()() as session:
        rows = list(
            (
                await session.execute(
                    select(Memory)
                    .where(Memory.status == "active", Memory.entity_key.isnot(None))
                    .order_by(Memory.entity_key, Memory.valid_from)
                )
            ).scalars()
        )
        by_key: dict[tuple[str, str], list[Memory]] = {}
        for m in rows:
            assert m.entity_key is not None
            by_key.setdefault((m.scope, m.entity_key), []).append(m)
        for group in by_key.values():
            for extra in group[1:]:  # keep the oldest-validity row active
                extra.status = "quarantined"
                extra.review_note = "contradiction sweep: duplicate active entity_key"
                quarantined += 1
        if quarantined:
            await session.commit()
    from app import obs

    obs.MEMORY_OPS.labels(kind="contradict", status="ok").inc()
    logger.info(
        "memory_contradiction_sweep", tier="memory", kind="contradict", quarantined=quarantined
    )
    return quarantined


async def _due(job_id: int, now: float) -> bool:
    last = _LAST_RUN.get(job_id)
    if last is None:
        return True  # never ran (or clock reset) ⇒ due now
    return (now - last) >= _INTERVALS_S[job_id]


async def run_due_jobs() -> dict[str, int]:
    """One periodic tick: run whichever jobs are due, advisory-locked."""
    from app.memory.procedural import mine_fallback_skills
    from app.memory.scheduler import acquire_job_lock, release_job_lock
    from app.registry_cache import get_cache

    if not await get_cache().setting("memory_enabled"):
        return {}
    results: dict[str, int] = {}
    now = asyncio.get_event_loop().time()
    from app.memory.episodic import compact_digests

    jobs = {
        JOB_DECAY: ("decay", decay_sweep),
        JOB_REFLECT: ("reflect", reflection),
        JOB_CONTRADICT: ("contradict", contradiction_sweep),
        JOB_COMPACT: ("compact", compact_digests),
    }
    for job_id, (name, fn) in jobs.items():
        if not await _due(job_id, now):
            continue
        async with get_session_factory()() as session:
            if not await acquire_job_lock(session, job_id):
                continue
            try:
                results[name] = await fn()
                _LAST_RUN[job_id] = now
            except Exception as exc:  # noqa: BLE001 — jobs never crash the loop
                logger.warning("memory_job_failed", job=name, error=str(exc))
            finally:
                await release_job_lock(session, job_id)
    if await _due(JOB_MINE, now):
        async with get_session_factory()() as session:
            if await acquire_job_lock(session, JOB_MINE):
                try:
                    results["mine"] = len(await mine_fallback_skills())
                    _LAST_RUN[JOB_MINE] = now
                except Exception as exc:  # noqa: BLE001
                    logger.warning("memory_job_failed", job="mine", error=str(exc))
                finally:
                    await release_job_lock(session, JOB_MINE)
    return results


async def run_periodic_loop(stop: asyncio.Event, tick_s: float = 60.0) -> None:
    """Lifespan-owned loop (spec §16.2): ticks are cheap when memory is off."""
    while not stop.is_set():
        try:
            await run_due_jobs()
        except Exception as exc:  # noqa: BLE001 — the loop must survive anything
            logger.warning("memory_periodic_tick_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_s)
        except TimeoutError:
            continue


def reset_job_clock() -> None:
    """Testing hook: make every job due immediately."""
    _LAST_RUN.clear()
