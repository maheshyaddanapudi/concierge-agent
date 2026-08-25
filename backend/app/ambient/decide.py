"""The decision plane (spec §17.3 — milestone M21): three tiers, strictly
ordered by cost. Tier 1 typed matchers (no model), tier 2 one significance
judgment (extraction role, per-intent override), tier 3 the run (wired in
M22 — here a 'fired' verdict is the hand-off record). Every decision writes
the fire/hold ledger. Silence is the default: anything unmatched holds.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import get_session_factory
from app.models import AmbientEvent, Routine, Run, StandingIntent

logger = structlog.get_logger("ambient")

_FIRE_SOURCES = {"webhook", "schedule", "manual", "wakeup"}


class SignificanceOutput(BaseModel):
    significant: bool
    urgency: int = Field(ge=1, le=5, default=2)
    reason: Literal["new_information", "matches_watch", "urgent_change", "routine", "noise"] = (
        "routine"
    )


def match_filters(payload: dict[str, Any] | None, filters: list[dict[str, Any]]) -> bool:
    """Tier-1 typed matchers: field + operator, the §17.3 set."""
    data = payload or {}
    for f in filters:
        raw: Any = data
        for part in str(f.get("field", "")).split("."):
            raw = raw.get(part) if isinstance(raw, dict) else None
        value = "" if raw is None else str(raw)
        expect = str(f.get("value", ""))
        op = f.get("op", "equals")
        ok = (
            value == expect
            if op == "equals"
            else expect in value
            if op == "contains"
            else value.startswith(expect)
            if op == "starts_with"
            else value in [str(v) for v in f.get("values", [])]
            if op == "one_of"
            else re.search(expect, value) is not None
            if op == "regex"
            else False
        )
        if not ok:
            return False
    return True


async def _runs_today_cap_reached() -> bool:
    from app.registry_cache import get_cache

    cap = int(await get_cache().setting("ambient_runs_per_day"))
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session_factory()() as session:
        count = (
            await session.execute(
                select(func.count()).where(
                    Run.trigger.isnot(None), Run.started_at >= midnight
                )
            )
        ).scalar_one()
    return count >= cap


async def _judge_significance(intent: StandingIntent, event: AmbientEvent) -> SignificanceOutput:
    """Tier 2: ONE structured call, extraction role unless the intent
    overrides. Any failure means held — silence is the default."""
    from app.llm import ModelParams, get_model
    from app.prompts import load_prompt
    from app.registry_cache import get_cache

    cache = get_cache()
    ref = (
        intent.judge_model_ref
        or await cache.setting("memory_extraction_model")
        or await cache.setting("default_model")
    )
    model = get_model(str(ref), ModelParams(effort="low"))
    structured = model.with_structured_output(SignificanceOutput)
    prompt = load_prompt("ambient_significance").format(
        watch=intent.text,
        predicate=intent.semantic_predicate or "(none)",
        event=str(event.payload)[:2000],
    )
    out = await structured.ainvoke(prompt)
    assert isinstance(out, SignificanceOutput)
    return out


async def process_event(event: AmbientEvent) -> tuple[str, str, dict[str, Any]]:
    """The drain's processor. Returns (verdict, reason, decision). The DRAIN
    writes all three onto the row it holds locked — a processor must never
    touch ambient_events itself (FOR UPDATE self-deadlock, found live)."""
    decision: dict[str, Any] = {"tier": 1}
    try:
        verdict, reason, decision = await _decide(event)
    except Exception as exc:  # noqa: BLE001 — fail-open to held
        verdict, reason = "held", f"decision error: {exc}"
    from app import obs

    obs.AMBIENT_OPS.labels(kind=verdict, status="ok").inc()
    logger.info(
        "ambient_decision",
        tier="ambient",
        kind=verdict,
        event_kind=event.kind,
        reason=reason[:120],
    )
    return (verdict, reason, decision)


async def _decide(event: AmbientEvent) -> tuple[str, str, dict[str, Any]]:
    decision: dict[str, Any] = {"tier": 1, "urgency": 2}

    # routine-addressed events (schedule/webhook/manual/wakeup)
    if event.routine_id is not None and event.source in _FIRE_SOURCES:
        async with get_session_factory()() as session:
            routine = await session.get(Routine, event.routine_id)
        if routine is None or routine.status != "active":
            return ("dropped", "routine missing or not active", decision)
        trig = (event.payload or {}).get("trigger") or {}
        filters = trig.get("filters") or []
        if filters and not match_filters((event.payload or {}).get("payload"), filters):
            return ("held", "tier-1 filters did not match", decision)
        if await _runs_today_cap_reached():
            return ("dropped", "ambient_runs_per_day cap reached", decision)
        decision["fired_for"] = "routine"
        return ("fired", "routine trigger matched", decision)

    # intent-addressed events (poll items, state conditions, patterns)
    if event.intent_id is not None:
        async with get_session_factory()() as session:
            intent = await session.get(StandingIntent, event.intent_id)
        if intent is None or intent.status != "active":
            return ("dropped", "intent missing or not active", decision)
        filters = (intent.compiled or {}).get("filters") or []
        if filters and not match_filters(event.payload, filters):
            return ("held", "tier-1 filters did not match", decision)
        if intent.semantic_predicate:
            decision["tier"] = 2
            try:
                judged = await _judge_significance(intent, event)
            except Exception as exc:  # noqa: BLE001 — judge failure ⇒ silence
                return ("held", f"significance judge failed: {exc}", decision)
            decision["urgency"] = judged.urgency
            decision["judge_reason"] = judged.reason
            if not judged.significant:
                return ("held", "judged not significant", decision)
        if await _runs_today_cap_reached():
            return ("dropped", "ambient_runs_per_day cap reached", decision)
        decision["fired_for"] = "intent"
        return ("fired", "intent condition met", decision)

    # presence + unaddressed internal events: bookkeeping, not runs
    if event.source in {"presence", "internal"}:
        return ("held", "informational event (no routine/intent addressee)", decision)
    return ("held", "no addressee", decision)


async def sweep_hitl_aging(now: datetime | None = None) -> int:
    """Internal-event emitter (spec §17.2): HITL items pending past the
    ambient timeout produce an internal event the platform can react to."""
    from app.ambient.store import emit_event
    from app.registry_cache import get_cache

    now = now or datetime.now(UTC)
    timeout_h = int(await get_cache().setting("ambient_hitl_timeout_h"))
    cutoff = now - timedelta(hours=timeout_h)
    emitted = 0
    async with get_session_factory()() as session:
        stale = list(
            (
                await session.execute(
                    select(Run).where(Run.status == "paused_hitl", Run.started_at <= cutoff)
                )
            ).scalars()
        )
    for run in stale:
        event = await emit_event(
            kind="hitl_aged",
            source="internal",
            payload={"run_id": str(run.id)},
            dedupe_key=f"hitl_aged:{run.id}",
        )
        if event is not None:
            emitted += 1
    return emitted
