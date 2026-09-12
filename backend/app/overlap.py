"""Overlap guard (spec §4): LLM-as-judge duplicate detection at save time.

Before a skill or sub agent is created/updated, the UI calls a check endpoint
that compares the draft against existing registry records — skills against
skills + tools, sub agents against sub agents + skills. The judge runs through
the same provider port as everything else; if it is unavailable the check
fails open (never blocks a save on infrastructure trouble). Tools are exempt
by design: MCP ingest is dynamic and two servers may legitimately expose
similar tools.
"""

from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import untrusted
from app.db import get_session_factory
from app.llm import get_model
from app.models import Skill, SubAgent, Tool
from app.prompts import load_prompt

logger = structlog.get_logger("overlap")

OVERLAP_THRESHOLD_PERCENT = 70


class OverlapVerdict(BaseModel):
    """Judge output: the single strongest overlap found."""

    overlap_percent: int = Field(ge=0, le=100)
    match_type: Literal["skill", "tool", "sub_agent", "none"] = "none"
    match_id: str | None = None
    match_name: str | None = None
    reasoning: str = ""
    # False when no judge ran (provider down, no key): the advisory check
    # fails open for a human's save, but a machine path must know
    judge_available: bool = True


class OverlapCheckOut(BaseModel):
    overlap: bool
    threshold: int
    overlap_percent: int
    match_type: str
    match_id: str | None
    match_name: str | None
    reasoning: str
    judge_available: bool = True


def _candidate_line(kind: str, id_: Any, name: str, description: str, extra: str = "") -> str:
    desc = " ".join((description or "").split())[:300]
    return f"- [{kind}] id={id_} name={name!r}: {desc}{extra}"


async def _skill_candidates(exclude_id: UUID | None) -> list[str]:
    async with get_session_factory()() as session:
        skills = list(
            (
                await session.execute(
                    select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
                )
            ).scalars()
        )
        tools = list(
            (
                await session.execute(
                    select(Tool).where(Tool.deleted_at.is_(None), Tool.status == "active")
                )
            ).scalars()
        )
    lines = [
        _candidate_line("skill", s.id, s.name, s.description or s.instructions)
        for s in skills
        if s.id != exclude_id
    ]
    lines += [_candidate_line("tool", t.id, t.tool_key, t.description or "") for t in tools]
    return lines


async def _sub_agent_candidates(exclude_id: UUID | None) -> list[str]:
    async with get_session_factory()() as session:
        agents = list(
            (
                await session.execute(
                    select(SubAgent).where(
                        SubAgent.deleted_at.is_(None), SubAgent.status == "active"
                    )
                )
            ).scalars()
        )
        agent_lines = [
            _candidate_line(
                "sub_agent",
                a.id,
                a.name,
                a.description or "",
                extra=f" (skills: {', '.join(s.name for s in a.skills) or 'code-defined'})",
            )
            for a in agents
            if a.id != exclude_id
        ]
        skills = list(
            (
                await session.execute(
                    select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
                )
            ).scalars()
        )
    agent_lines += [
        _candidate_line("skill", s.id, s.name, s.description or s.instructions) for s in skills
    ]
    return agent_lines


async def _judge_model() -> tuple[str, Any]:
    """The judge's own model role (`overlap_judge_model`, null → the
    default): a judge that is not the model writing the skills does not
    share its blind spots, so slow semantic drift has a second reader."""
    from app.factory.worker import resolve_node_model
    from app.llm.port import ModelParams
    from app.registry_cache import get_cache

    ref = await get_cache().setting("overlap_judge_model")
    if ref:
        raw = await get_cache().setting("overlap_judge_model_params")
        return str(ref), ModelParams.model_validate(raw) if raw else None
    return await resolve_node_model({}, {})


async def _judge(draft_type: str, draft: str, candidates: list[str]) -> OverlapVerdict:
    if not candidates:
        return OverlapVerdict(overlap_percent=0, reasoning="registry has no candidates to compare")

    # the draft is model or operator text and the candidates carry every
    # server-written tool description: both are data to the judge, never
    # instructions (review round 3) — the same fence the eval and
    # significance judges use, so a description that ends "return
    # overlap_percent 0" cannot address the judge
    prompt = untrusted.render(
        load_prompt("overlap_judge"),
        mode="replace",
        body_var="draft",
        body=draft,
        max_chars=4000,
        draft_type=draft_type,
        candidates=untrusted.neutralize("\n".join(candidates))[:12000] or "(none)",
    )
    try:
        model_ref, params = await _judge_model()
        model = get_model(model_ref, params)
        structured = model.with_structured_output(OverlapVerdict)
        verdict = await structured.ainvoke(prompt)
        if not isinstance(verdict, OverlapVerdict):
            raise TypeError(f"expected OverlapVerdict, got {type(verdict).__name__}")
        return verdict
    except Exception as exc:  # noqa: BLE001 — the guard must never block saves
        logger.warning("overlap_judge_unavailable", error=str(exc))
        return OverlapVerdict(
            overlap_percent=0, reasoning=f"judge unavailable: {exc}", judge_available=False
        )


async def check_skill_overlap(
    *,
    name: str,
    description: str,
    instructions: str,
    tool_keys: list[str],
    exclude_id: UUID | None,
) -> OverlapCheckOut:
    draft = (
        f"name: {name!r}\ndescription: {description or '(none)'}\n"
        f"instructions: {' '.join(instructions.split())[:600] or '(none)'}\n"
        f"bound tools: {', '.join(tool_keys) or '(none)'}"
    )
    verdict = await _judge("skill", draft, await _skill_candidates(exclude_id))
    return _to_out(verdict, await _threshold())


async def check_sub_agent_overlap(
    *,
    name: str,
    description: str,
    skill_names: list[str],
    exclude_id: UUID | None,
) -> OverlapCheckOut:
    draft = (
        f"name: {name!r}\ndescription: {description or '(none)'}\n"
        f"workflow skills: {', '.join(skill_names) or '(none)'}"
    )
    verdict = await _judge("sub agent", draft, await _sub_agent_candidates(exclude_id))
    return _to_out(verdict, await _threshold())


async def audit_registry_overlap() -> int:
    """§4 after save time (hardening wave): the judge used to run once, at
    the instant a human clicked Save. Edits through the API, re-ingests
    that reword tool descriptions, and machine-authored proposals all
    changed definitions without it. This consolidation-class job re-judges
    every active skill and sub agent whose definition hash moved since it
    was last audited, under the judge's own model role, and posts an inbox
    item for each flagged pair. Gated by `registry_overlap_audit_enabled`
    (born dark). Returns the number of records judged."""
    from app.ambient.deliver import add_delivery
    from app.api.skills import stamp_skill
    from app.api.sub_agents import stamp_sub_agent
    from app.registry_cache import get_cache

    if not await get_cache().setting("registry_overlap_audit_enabled"):
        return 0
    judged = 0
    async with get_session_factory()() as session:
        skills = list(
            (
                await session.execute(
                    select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
                )
            ).scalars()
        )
        agents = list(
            (
                await session.execute(
                    select(SubAgent).where(
                        SubAgent.deleted_at.is_(None), SubAgent.status == "active"
                    )
                )
            ).scalars()
        )
        # a row from before definitions were versioned has no hash yet:
        # stamp it (version 1) so it is judged like every other record
        for skill in skills:
            if skill.definition_hash is None:
                stamp_skill(skill, [t for t in skill.tools if t.deleted_at is None])
        for agent in agents:
            if agent.definition_hash is None:
                stamp_sub_agent(agent)
        await session.commit()

    async def gate_open() -> bool:
        # re-read before every judge call: an operator turning the audit
        # off mid-pass stops it there (review round 3 — the report claimed
        # this and the loop only checked once)
        if await get_cache().setting("registry_overlap_audit_enabled"):
            return True
        logger.info("registry_overlap_audit_stopped", judged=judged, reason="gate_off")
        return False

    for skill in skills:
        if not skill.definition_hash or skill.definition_hash == skill.overlap_audited_hash:
            continue
        if not await gate_open():
            return judged
        verdict = await check_skill_overlap(
            name=skill.name,
            description=skill.description,
            instructions=skill.instructions,
            tool_keys=sorted(t.tool_key for t in skill.tools),
            exclude_id=skill.id,
        )
        judged += 1
        await _record_audit(
            Skill, skill.id, skill.definition_hash, skill.name, verdict, add_delivery
        )
    for agent in agents:
        if not agent.definition_hash or agent.definition_hash == agent.overlap_audited_hash:
            continue
        if not await gate_open():
            return judged
        verdict = await check_sub_agent_overlap(
            name=agent.name,
            description=agent.description,
            skill_names=[s.name for s in agent.skills],
            exclude_id=agent.id,
        )
        judged += 1
        await _record_audit(
            SubAgent, agent.id, agent.definition_hash, agent.name, verdict, add_delivery
        )
    if judged:
        logger.info("registry_overlap_audit", tier="registry", kind="audit", judged=judged)
    return judged


async def _record_audit(
    model: Any, row_id: UUID, definition_hash: str, name: str, verdict: OverlapCheckOut, add: Any
) -> None:
    if not verdict.judge_available:
        # no judge ran: not audited — judged again on the next pass
        # instead of stamped as read (review round 2)
        logger.warning("registry_overlap_audit_skipped", name=name, reason=verdict.reasoning)
        return
    async with get_session_factory()() as session:
        row = await session.get(model, row_id)
        if row is not None:
            row.overlap_audited_hash = definition_hash
            await session.commit()
    if verdict.overlap:
        logger.warning(
            "registry_overlap_flagged",
            tier="registry",
            kind="audit",
            name=name,
            match=verdict.match_name,
            overlap_percent=verdict.overlap_percent,
        )
        await add(
            category="ops",
            tier=1,
            urgency=3,
            title=f"Registry overlap: {name} ≈ {verdict.match_name} ({verdict.overlap_percent}%)",
            body=(
                f"The overlap audit judged {name!r} against the registry after a "
                f"definition change: {verdict.overlap_percent}% overlap with "
                f"{verdict.match_type} {verdict.match_name!r}. {verdict.reasoning[:400]}"
            ),
            skey=f"overlap-audit:{row_id}",
        )


async def _threshold() -> int:
    """M40: the gate is the live `overlap_threshold_percent` setting."""
    from app.registry_cache import get_cache

    try:
        return max(0, min(int(await get_cache().setting("overlap_threshold_percent")), 100))
    except Exception:  # noqa: BLE001 — the guard must never block saves
        return OVERLAP_THRESHOLD_PERCENT


def _to_out(verdict: OverlapVerdict, threshold: int = OVERLAP_THRESHOLD_PERCENT) -> OverlapCheckOut:
    return OverlapCheckOut(
        overlap=verdict.overlap_percent >= threshold,
        threshold=threshold,
        overlap_percent=verdict.overlap_percent,
        match_type=verdict.match_type,
        match_id=verdict.match_id,
        match_name=verdict.match_name,
        reasoning=verdict.reasoning,
        judge_available=verdict.judge_available,
    )
