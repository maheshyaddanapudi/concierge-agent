"""Ambient native tools (spec §17.4) — registry citizens.

Two families: agent wakeups (H2 — `ambient.wakeup` / `ambient.cancel_wakeup`,
callable only from inside an ambient routine run; the platform clamps and
caps), and standing watches (`ambient.watch` compile-echo-confirm →
`ambient.confirm_watch` / `ambient.unwatch`, callable from any run so a chat
user can say "tell me when…"). All are inert while `ambient_enabled` is
false — byte-identity when dark.
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.native.provider import native_tool


class WatchFilter(BaseModel):
    field: str
    op: Literal["equals", "contains", "starts_with", "one_of", "regex"] = "equals"
    value: str = ""
    values: list[str] = Field(default_factory=list)


class WatchCompile(BaseModel):
    """The compiler's structured output: one typed rule + the echo line."""

    mode: Literal["events", "poll", "state"]
    filters: list[WatchFilter] = Field(default_factory=list)
    poll_source: str | None = None
    probe: str | None = None
    op: Literal[">=", "<=", "=="] = ">="
    value: float = 0.0
    semantic_predicate: str | None = None
    cadence_s: int = 300
    echo: str


async def _ambient_on() -> bool:
    from app.registry_cache import get_cache

    return bool(await get_cache().setting("ambient_enabled"))


async def _current_ambient_routine_id() -> UUID | None:
    """The routine that owns the current run, via trigger provenance."""
    from app.db import get_session_factory
    from app.models import Run
    from app.orchestrator.context import get_run_context

    ctx = get_run_context()
    if ctx is None:
        return None
    async with get_session_factory()() as session:
        run = await session.get(Run, ctx.run_id)
    if run is None or not run.trigger:
        return None
    raw = run.trigger.get("routine_id")
    return UUID(str(raw)) if raw else None


@native_tool(
    "ambient.wakeup",
    "Schedule a future self-wakeup for this ambient routine (heartbeat H2). "
    "Provide reason plus delay_s (seconds from now) or at (ISO timestamp). "
    "The platform clamps delays to [60s, 24h] and caps pending and daily "
    "wakeups; at fire time a done-guard expires wakeups a later completed "
    "run has superseded. Only callable from inside an ambient routine run.",
)
async def ambient_wakeup(
    reason: str, delay_s: int | None = None, at: str | None = None
) -> dict[str, Any]:
    from app.ambient.wakeups import WakeupCapError, schedule_wakeup
    from app.orchestrator.context import get_run_context

    if not await _ambient_on():
        return {"scheduled": False, "error": "ambient mode is disabled (ambient_enabled=false)"}
    routine_id = await _current_ambient_routine_id()
    if routine_id is None:
        return {
            "scheduled": False,
            "error": "only ambient routine runs may schedule wakeups",
        }
    ctx = get_run_context()
    try:
        wakeup = await schedule_wakeup(
            routine_id,
            delay_s=delay_s,
            at=at,
            reason=reason,
            created_by="agent",
            run_id=ctx.run_id if ctx else None,
        )
    except (WakeupCapError, ValueError) as exc:
        return {"scheduled": False, "error": str(exc)}
    return {
        "scheduled": True,
        "wakeup_id": str(wakeup.id),
        "due_at": wakeup.due_at.isoformat(),
        "note": "delay is clamped to [60s, 24h]",
    }


@native_tool(
    "ambient.cancel_wakeup",
    "Cancel one of this routine's pending wakeups by id (from ambient.wakeup).",
)
async def ambient_cancel_wakeup(wakeup_id: str) -> dict[str, Any]:
    from app.ambient.wakeups import cancel_wakeup
    from app.db import get_session_factory
    from app.models import AmbientWakeup

    if not await _ambient_on():
        return {"cancelled": False, "error": "ambient mode is disabled (ambient_enabled=false)"}
    routine_id = await _current_ambient_routine_id()
    if routine_id is None:
        return {"cancelled": False, "error": "only ambient routine runs may cancel wakeups"}
    try:
        target = UUID(wakeup_id)
    except ValueError:
        return {"cancelled": False, "error": f"'{wakeup_id}' is not a wakeup id"}
    async with get_session_factory()() as session:
        wakeup = await session.get(AmbientWakeup, target)
    if wakeup is None or wakeup.routine_id != routine_id:
        return {"cancelled": False, "error": "no such wakeup for this routine"}
    ok = await cancel_wakeup(target)
    return {"cancelled": ok} if ok else {"cancelled": False, "error": "wakeup is not pending"}


@native_tool(
    "ambient.watch",
    "Create a standing watch from a natural-language request ('tell me when "
    "…'). The request is compiled ONCE into a typed rule; the interpretation "
    "is echoed back and the watch stays in 'proposed' status until the user "
    "confirms it via ambient.confirm_watch. Never activates silently.",
)
async def ambient_watch(text: str) -> dict[str, Any]:
    from app.ambient.triggers import registered_poll_sources, registered_state_probes
    from app.db import get_session_factory
    from app.llm import ModelParams, get_model
    from app.models import StandingIntent
    from app.prompts import load_prompt
    from app.registry_cache import get_cache

    if not await _ambient_on():
        return {"status": "rejected", "error": "ambient mode is disabled (ambient_enabled=false)"}
    cache = get_cache()
    ref = await cache.setting("memory_extraction_model") or await cache.setting("default_model")
    model = get_model(str(ref), ModelParams(effort="low"))
    prompt = load_prompt("ambient_watch_compile").format(
        text=text[:2000],
        poll_sources=", ".join(sorted(registered_poll_sources())) or "(none registered)",
        state_probes=", ".join(sorted(registered_state_probes())) or "(none registered)",
    )
    try:
        out = await model.with_structured_output(WatchCompile).ainvoke(prompt)
        assert isinstance(out, WatchCompile)
    except Exception as exc:  # noqa: BLE001 — compile failure is a clean refusal
        return {"status": "rejected", "error": f"could not compile the watch: {exc}"}

    compiled: dict[str, Any]
    if out.mode == "state":
        if not out.probe or out.probe not in registered_state_probes():
            return {"status": "rejected", "error": f"unknown state probe: {out.probe!r}"}
        condition_type = "state"
        compiled = {"probe": out.probe, "op": out.op, "value": out.value}
    elif out.mode == "poll":
        if not out.poll_source or out.poll_source not in registered_poll_sources():
            return {"status": "rejected", "error": f"unknown poll source: {out.poll_source!r}"}
        condition_type = "event"
        compiled = {
            "poll": {"source": out.poll_source},
            "filters": [f.model_dump() for f in out.filters],
        }
    else:
        if not out.filters:
            return {
                "status": "rejected",
                "error": "an events watch needs at least one filter — a filterless watch "
                "would fire on everything (if this is a recurring task, create a "
                "routine schedule instead)",
            }
        condition_type = "event"
        compiled = {"match": "events", "filters": [f.model_dump() for f in out.filters]}

    async with get_session_factory()() as session:
        intent = StandingIntent(
            text=text[:2000],
            condition_type=condition_type,
            compiled=compiled,
            semantic_predicate=out.semantic_predicate,
            base_interval_s=max(out.cadence_s, 60),
            current_interval_s=max(out.cadence_s, 60),
            status="proposed",
        )
        session.add(intent)
        await session.commit()
        await session.refresh(intent)
    return {
        "status": "proposed",
        "intent_id": str(intent.id),
        "interpretation": out.echo,
        "compiled": compiled,
        "note": "ask the user to confirm, then call ambient.confirm_watch with this intent_id",
    }


@native_tool(
    "ambient.confirm_watch",
    "Activate a proposed standing watch after the user confirms the echoed "
    "interpretation. Pass the intent id from ambient.watch, or leave it "
    "empty to confirm the most recently proposed watch.",
)
async def ambient_confirm_watch(intent_id: str = "") -> dict[str, Any]:
    from sqlalchemy import select

    from app.db import get_session_factory
    from app.models import StandingIntent

    async with get_session_factory()() as session:
        if intent_id:
            try:
                target = UUID(intent_id)
            except ValueError:
                return {"status": "rejected", "error": f"'{intent_id}' is not an intent id"}
            intent = await session.get(StandingIntent, target)
        else:
            intent = (
                await session.execute(
                    select(StandingIntent)
                    .where(StandingIntent.status == "proposed")
                    .order_by(StandingIntent.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if intent is None or intent.status != "proposed":
            return {"status": "rejected", "error": "no proposed watch to confirm"}
        intent.status = "active"
        confirmed_id = str(intent.id)
        echo = intent.text
        await session.commit()
    return {"status": "active", "intent_id": confirmed_id, "watch": echo}


@native_tool(
    "ambient.unwatch",
    "Retire a standing watch by id — it stops being evaluated but stays "
    "auditable. Works on proposed and active watches.",
)
async def ambient_unwatch(intent_id: str) -> dict[str, Any]:
    from app.db import get_session_factory
    from app.models import StandingIntent

    try:
        target = UUID(intent_id)
    except ValueError:
        return {"retired": False, "error": f"'{intent_id}' is not an intent id"}
    async with get_session_factory()() as session:
        intent = await session.get(StandingIntent, target)
        if intent is None or intent.status not in {"proposed", "active"}:
            return {"retired": False, "error": "no proposed or active watch with that id"}
        intent.status = "retired"
        await session.commit()
    return {"retired": True, "intent_id": intent_id}
