"""Sub agents registry API (spec §4, §3.4, §3.5)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import (
    FiltersDep,
    SessionDep,
    apply_filters,
    enforce_static_rules,
    fetch_or_404,
    reject_static_delete,
)
from app.factory.dag import validate_workflow, workflow_skill_ids
from app.llm import ModelParams, validate_model_selection
from app.models import Skill, SubAgent
from app.schemas.sub_agent import SubAgentCreate, SubAgentOut, SubAgentPatch, ValidateResult

router = APIRouter(prefix="/sub-agents", tags=["sub-agents"])


def _validate_model_fields(model: str | None, model_params: dict[str, Any] | None) -> None:
    if model_params is not None and model is None:
        raise HTTPException(status_code=422, detail="model_params requires model to be set")
    if model is not None:
        try:
            params = ModelParams.model_validate(model_params) if model_params else None
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid model_params: {exc}") from exc
        errors = validate_model_selection(model, params)
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))


async def _active_skill_ids(session: SessionDep) -> set[str]:
    stmt = select(Skill.id).where(Skill.deleted_at.is_(None), Skill.status == "active")
    return {str(sid) for sid in (await session.execute(stmt)).scalars()}


async def _validate_and_resolve(session: SessionDep, workflow: dict[str, Any]) -> list[Skill]:
    """Structural DAG validation (spec §3.5) + full factory compile (spec §6:
    compile-time = save-time) + skill resolution; 422 on errors."""
    errors = validate_workflow(workflow, await _active_skill_ids(session))
    if not errors:
        from app.factory.worker import compile_workflow_check

        errors = await compile_workflow_check(session, workflow)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    ids = [UUID(sid) for sid in workflow_skill_ids(workflow)]
    if not ids:
        return []
    return list((await session.execute(select(Skill).where(Skill.id.in_(ids)))).scalars())


@router.get("", response_model=list[SubAgentOut])
async def list_sub_agents(session: SessionDep, filters: FiltersDep) -> list[SubAgent]:
    stmt = apply_filters(select(SubAgent), SubAgent, filters)
    return list((await session.execute(stmt)).scalars())


@router.post("", response_model=SubAgentOut, status_code=201)
async def create_sub_agent(body: SubAgentCreate, session: SessionDep) -> SubAgent:
    _validate_model_fields(body.model, body.model_params)
    skills = await _validate_and_resolve(session, body.workflow)
    agent = SubAgent(
        name=body.name,
        description=body.description,
        persona=body.persona,
        model=body.model,
        model_params=body.model_params,
        workflow=body.workflow,
        kind="custom",
        source="dynamic",
        skills=skills,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=SubAgentOut)
async def get_sub_agent(agent_id: UUID, session: SessionDep) -> SubAgent:
    return await fetch_or_404(session, SubAgent, agent_id)


@router.patch("/{agent_id}", response_model=SubAgentOut)
async def patch_sub_agent(agent_id: UUID, body: SubAgentPatch, session: SessionDep) -> SubAgent:
    agent = await fetch_or_404(session, SubAgent, agent_id)
    changes = body.model_dump(exclude_unset=True)
    enforce_static_rules(agent, set(changes))
    if agent.kind == "native" and ("workflow" in changes or "persona" in changes):
        raise HTTPException(
            status_code=403, detail="native sub agents are code-defined; only status is editable"
        )
    model = changes.get("model", agent.model)
    model_params = changes.get("model_params", agent.model_params)
    _validate_model_fields(model, model_params)
    if "workflow" in changes:
        agent.skills = await _validate_and_resolve(session, changes["workflow"])
    for f, v in changes.items():
        setattr(agent, f, v)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.post("/{agent_id}/validate", response_model=ValidateResult)
async def validate_sub_agent(agent_id: UUID, session: SessionDep) -> ValidateResult:
    """Dry-run factory compile (spec §4, §6)."""
    agent = await fetch_or_404(session, SubAgent, agent_id)
    if agent.kind == "native":
        return ValidateResult(valid=True, errors=[])
    errors = validate_workflow(agent.workflow, await _active_skill_ids(session))
    if not errors:
        from app.factory.worker import compile_workflow_check

        errors = await compile_workflow_check(session, agent.workflow or {})
    return ValidateResult(valid=not errors, errors=errors)


@router.delete("/{agent_id}", status_code=204)
async def delete_sub_agent(agent_id: UUID, session: SessionDep) -> None:
    agent = await fetch_or_404(session, SubAgent, agent_id)
    reject_static_delete(agent)
    agent.deleted_at = datetime.now(UTC)
    await session.commit()
