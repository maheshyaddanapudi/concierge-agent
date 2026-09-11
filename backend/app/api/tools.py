"""Tools registry API (spec §4). Tools are created by MCP ingestion or the
native scan — never via API."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import (
    FiltersDep,
    SessionDep,
    apply_filters,
    enforce_static_rules,
    fetch_or_404,
)
from app.models import Skill, Tool, skill_tools
from app.registry_cache import get_cache
from app.retrieval import schedule_embedding
from app.schemas.skill import SkillOut
from app.schemas.tool import ToolOut, ToolPatch

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
async def list_tools(session: SessionDep, filters: FiltersDep) -> list[Tool]:
    stmt = apply_filters(select(Tool), Tool, filters)
    return list((await session.execute(stmt)).scalars())


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: UUID, session: SessionDep) -> Tool:
    return await fetch_or_404(session, Tool, tool_id)


@router.patch("/{tool_id}", response_model=ToolOut)
async def patch_tool(tool_id: UUID, body: ToolPatch, session: SessionDep) -> Tool:
    tool = await fetch_or_404(session, Tool, tool_id)
    changes = body.model_dump(exclude_unset=True)
    enforce_static_rules(tool, set(changes))
    if "tool_key" in changes and changes["tool_key"] != tool.tool_key:
        from app.factory.worker import sanitize_tool_name

        new_key = str(changes["tool_key"])
        others = (await session.execute(select(Tool).where(Tool.id != tool.id))).scalars()
        for other in others:
            if other.tool_key == new_key:
                raise HTTPException(
                    status_code=409, detail=f"tool_key {new_key!r} is already in use"
                )
            if sanitize_tool_name(other.tool_key) == sanitize_tool_name(new_key):
                # the LLM-facing name is the sanitized key: two keys that
                # sanitize alike would bind first-wins, the other silently
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"tool_key {new_key!r} binds under the same name as "
                        f"{other.tool_key!r} ({sanitize_tool_name(new_key)!r})"
                    ),
                )
        # spec §3.2: bindings survive a rename (they use the id) — the
        # `{tool:old.key}` mentions in skill instructions do not, so a rename
        # that would leave a skill naming a tool it no longer has is refused
        # with the skills to fix first
        mentioning = [
            s.name
            for s in await _skills_of_tool(session, tool.id)
            if f"{{tool:{tool.tool_key}}}" in (s.instructions or "")
        ]
        if mentioning:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"skills mention {{tool:{tool.tool_key}}} in their instructions: "
                    f"{', '.join(sorted(mentioning))} — update the mentions first"
                ),
            )
    renamed = "tool_key" in changes and changes["tool_key"] != tool.tool_key
    if "description" in changes and changes["description"] != tool.description:
        # an operator's wording survives re-ingests (hardening wave)
        from app.toolschema import apply_description

        apply_description(tool, str(changes.pop("description")), source="operator")
    if changes.get("description_source") == "server":
        # the operator hands the wording back: the next ingest re-adopts the
        # server's text as a first sighting (review round 2)
        tool.description_source = "server"
        tool.description_hash = None
    changes.pop("description_source", None)
    for f, v in changes.items():
        setattr(tool, f, v)
    await session.commit()
    await session.refresh(tool)
    await get_cache().invalidate("tools")
    schedule_embedding("tools", str(tool.id))
    if renamed:
        from app.retrieval import schedule_dependents

        schedule_dependents("tools", str(tool.id))  # skills embed their tool keys
    return tool


async def _skills_of_tool(session: SessionDep, tool_id: UUID) -> list[Skill]:
    stmt = (
        select(Skill)
        .join(skill_tools, skill_tools.c.skill_id == Skill.id)
        .where(skill_tools.c.tool_id == tool_id, Skill.deleted_at.is_(None))
        .order_by(Skill.name)
    )
    return list((await session.execute(stmt)).scalars())


@router.get("/{tool_id}/skills", response_model=list[SkillOut])
async def tool_skills(tool_id: UUID, session: SessionDep) -> list[Skill]:
    await fetch_or_404(session, Tool, tool_id)
    return await _skills_of_tool(session, tool_id)


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: UUID, session: SessionDep) -> None:
    tool = await fetch_or_404(session, Tool, tool_id)
    if tool.source == "static":
        raise HTTPException(
            status_code=403,
            detail="static records cannot be deleted; toggle status to 'inactive' instead",
        )
    dependents = await _skills_of_tool(session, tool_id)
    if dependents:
        raise HTTPException(
            status_code=409,
            detail="tool is bound to skills: " + ", ".join(sorted(s.name for s in dependents)),
        )
    tool.deleted_at = datetime.now(UTC)
    await session.commit()
    await get_cache().invalidate("tools")


@router.post("/{tool_id}/restore", response_model=ToolOut)
async def restore_tool(tool_id: UUID, session: SessionDep) -> Tool:
    """Undo a soft delete (M53): since re-ingest no longer resurrects a
    deleted MCP tool, restoring one is an explicit operator act."""
    tool = await session.get(Tool, tool_id)  # a deleted row is exactly the one to fetch
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool.deleted_at is None:
        return tool
    tool.deleted_at = None
    await session.commit()
    await session.refresh(tool)
    await get_cache().invalidate("tools")
    return tool


@router.post("/{tool_id}/acknowledge-schema", response_model=ToolOut)
async def acknowledge_schema_change(tool_id: UUID, session: SessionDep) -> Tool:
    """The operator has read a schema change (spec §3.2 drift): the flag
    clears, and a tool the quarantine policy took out of service is back
    in service. The version and hash stay — they are the record."""
    from app.toolschema import acknowledge_schema

    tool = await session.get(Tool, tool_id)
    if tool is None or tool.deleted_at is not None:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool.schema_changed_at is None and tool.ingest_state != "changed":
        return tool
    acknowledge_schema(tool)
    await session.commit()
    await session.refresh(tool)
    await get_cache().invalidate("tools")
    return tool
