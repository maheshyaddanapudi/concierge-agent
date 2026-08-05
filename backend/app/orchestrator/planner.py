"""Graph-mode planner (spec §7.1): progressive disclosure + structured output
+ validate → repair-once → fail."""

from typing import Any, Literal
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, SubAgent, Tool
from app.prompts import load_prompt


class PlanCapability(BaseModel):
    type: Literal["direct_tool", "direct_skill", "sub_agent", "spin_worker"]
    id: str | None = None
    skill_ids: list[str] | None = None


class PlanEntry(BaseModel):
    id: str
    capability: PlanCapability
    task: str
    depends_on: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Planner structured output: entries, or a direct answer, or an explicit
    no-confident-match signal (→ full-catalog fallback, spec §7.0)."""

    entries: list[PlanEntry] = Field(default_factory=list)
    direct_answer: str | None = None
    no_confident_match: bool = False


async def registry_summaries(session: AsyncSession) -> dict[str, Any]:
    """Compact registry summaries only (progressive disclosure)."""
    agents = list(
        (
            await session.execute(
                select(SubAgent).where(SubAgent.deleted_at.is_(None), SubAgent.status == "active")
            )
        ).scalars()
    )
    cards = [
        {
            "id": str(a.id),
            "name": a.name,
            "description": a.description,
            "skills": [s.name for s in a.skills],
        }
        for a in agents
    ]
    tools = list(
        (
            await session.execute(
                select(Tool).where(
                    Tool.deleted_at.is_(None),
                    Tool.status == "active",
                    Tool.direct_exposure.is_(True),
                )
            )
        ).scalars()
    )
    skills = list(
        (
            await session.execute(
                select(Skill).where(
                    Skill.deleted_at.is_(None),
                    Skill.status == "active",
                    Skill.direct_exposure.is_(True),
                )
            )
        ).scalars()
    )
    direct = [
        {"id": str(t.id), "type": "direct_tool", "name": t.tool_key, "description": t.description}
        for t in tools
    ] + [
        {"id": str(s.id), "type": "direct_skill", "name": s.name, "description": s.description}
        for s in skills
    ]
    return {"sub_agent_cards": cards, "direct_capabilities": direct}


async def validate_plan(session: AsyncSession, plan: PlannerOutput, max_steps: int) -> list[str]:
    """Schema is enforced by structured output; this checks referenced ids
    against the registries (spec §7.1)."""
    errors: list[str] = []
    if len(plan.entries) > max_steps:
        errors.append(f"plan has {len(plan.entries)} entries; max_plan_steps is {max_steps}")
    seen_ids = {e.id for e in plan.entries}
    if len(seen_ids) != len(plan.entries):
        errors.append("entry ids must be unique")
    for entry in plan.entries:
        for dep in entry.depends_on:
            if dep not in seen_ids:
                errors.append(f"entry {entry.id!r} depends on unknown entry {dep!r}")
            if dep == entry.id:
                errors.append(f"entry {entry.id!r} depends on itself")
        cap = entry.capability
        if cap.type == "spin_worker":
            if not cap.skill_ids:
                errors.append(f"entry {entry.id!r}: spin_worker requires skill_ids")
                continue
            for sid in cap.skill_ids:
                if not await _exists(session, Skill, sid):
                    errors.append(f"entry {entry.id!r}: unknown skill id {sid!r}")
        else:
            if not cap.id:
                errors.append(f"entry {entry.id!r}: capability requires an id")
                continue
            model = {
                "direct_tool": Tool,
                "direct_skill": Skill,
                "sub_agent": SubAgent,
            }[cap.type]
            if not await _exists(session, model, cap.id):
                errors.append(f"entry {entry.id!r}: unknown {cap.type} id {cap.id!r}")
    return errors


async def _exists(session: AsyncSession, model: type[Any], raw_id: str) -> bool:
    try:
        record_id = UUID(raw_id)
    except ValueError:
        return False
    record = await session.get(model, record_id)
    return record is not None and record.deleted_at is None and record.status == "active"


def build_planner_prompt(
    task: str,
    history: str,
    summaries: dict[str, Any],
    max_plan_steps: int,
) -> str:
    def fmt_cards(cards: list[dict[str, Any]]) -> str:
        if not cards:
            return "(none)"
        return "\n".join(
            f"- id={c['id']} name={c['name']} skills={c['skills']}: {c['description']}"
            for c in cards
        )

    def fmt_direct(items: list[dict[str, Any]]) -> str:
        if not items:
            return "(none)"
        return "\n".join(
            f"- id={i['id']} type={i['type']} name={i['name']}: {i['description']}" for i in items
        )

    return load_prompt("planner").format(
        task=task,
        history=history or "(new conversation)",
        sub_agent_cards=fmt_cards(summaries["sub_agent_cards"]),
        direct_capabilities=fmt_direct(summaries["direct_capabilities"]),
        max_plan_steps=max_plan_steps,
    )


class PlanFailure(RuntimeError):
    def __init__(self, errors: list[str], raw_outputs: list[Any]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.raw_outputs = raw_outputs


async def run_planner(
    session: AsyncSession,
    model: BaseChatModel,
    task: str,
    history: str,
    max_plan_steps: int,
) -> tuple[PlannerOutput, list[Any], dict[str, int]]:
    """Plan → validate → one repair retry → fail (spec §7.1). Returns the
    validated plan, raw outputs (for debugging storage), and token usage."""
    summaries = await registry_summaries(session)
    prompt = build_planner_prompt(task, history, summaries, max_plan_steps)
    structured = model.with_structured_output(PlannerOutput, include_raw=True)
    raw_outputs: list[Any] = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    errors: list[str] = []
    attempt_prompt = prompt
    for _ in range(2):
        result: dict[str, Any] = await structured.ainvoke(attempt_prompt)  # type: ignore[assignment]
        raw = result.get("raw")
        raw_outputs.append(getattr(raw, "content", None) or str(getattr(raw, "tool_calls", "")))
        meta = getattr(raw, "usage_metadata", None)
        if meta:
            usage["input_tokens"] += meta.get("input_tokens", 0)
            usage["output_tokens"] += meta.get("output_tokens", 0)
        parsed = result.get("parsed")
        if parsed is None:
            err = result.get("parsing_error")
            errors = [f"planner output failed schema validation: {err}"]
        else:
            try:
                plan = PlannerOutput.model_validate(parsed)
            except ValidationError as exc:
                errors = [f"planner output failed schema validation: {exc}"]
            else:
                errors = await validate_plan(session, plan, max_plan_steps)
                if not errors:
                    return plan, raw_outputs, usage
        attempt_prompt = (
            prompt
            + "\n\nYour previous plan was invalid. Fix these errors and try again:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
    raise PlanFailure(errors, raw_outputs)
