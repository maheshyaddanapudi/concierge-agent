"""MCP servers registry API (spec §4, §5)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app import egress
from app.api.deps import (
    FiltersDep,
    SessionDep,
    apply_filters,
    enforce_static_rules,
    fetch_or_404,
    reject_static_delete,
)
from app.mcp.secrets import mask_map, merge_secret_map
from app.models import McpServer, Skill, Tool, skill_tools
from app.schemas.mcp_server import McpServerCreate, McpServerOut, McpServerPatch

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


async def _tool_counts(session: SessionDep, server_ids: list[UUID]) -> dict[UUID, int]:
    if not server_ids:
        return {}
    rows = await session.execute(
        select(Tool.mcp_server_id, func.count())
        .where(Tool.mcp_server_id.in_(server_ids), Tool.deleted_at.is_(None))
        .group_by(Tool.mcp_server_id)
    )
    return {sid: count for sid, count in rows if sid is not None}


logger = structlog.get_logger("mcp")


def _to_out(server: McpServer, tool_count: int = 0) -> McpServerOut:
    out = McpServerOut.model_validate(server)
    out.tool_count = tool_count
    # M52: env and headers are write-only — the API never returns a value
    out.env = mask_map(server.env)
    out.headers = mask_map(server.headers)
    return out


def _check_egress(url: str | None) -> None:
    """Save-time half of the egress policy (M52): the static checks, so a
    private or non-http target is refused with a 422 instead of a
    connection attempt; the resolved-address check runs at connect time."""
    if not url:
        return
    try:
        egress.check_url_static(url)
    except egress.EgressError as exc:
        raise HTTPException(422, f"url refused by the egress policy ({exc.kind})") from exc


@router.get("", response_model=list[McpServerOut])
async def list_servers(session: SessionDep, filters: FiltersDep) -> list[McpServerOut]:
    stmt = apply_filters(select(McpServer), McpServer, filters)
    servers = list((await session.execute(stmt)).scalars())
    counts = await _tool_counts(session, [s.id for s in servers])
    return [_to_out(s, counts.get(s.id, 0)) for s in servers]


@router.post("", response_model=McpServerOut, status_code=201)
async def create_server(body: McpServerCreate, session: SessionDep) -> McpServerOut:
    if body.transport == "http":
        _check_egress(body.url)
    server = McpServer(
        **body.model_dump(),
        source="dynamic",
        # registered but not yet connected; the MCP manager flips this to
        # active/error when it connects (spec §5)
        status="inactive",
    )
    from app.mcp.manager import config_fingerprint

    server.config_hash = config_fingerprint(server)  # stamped at birth, not at first success
    session.add(server)
    await session.commit()
    from app.mcp.manager import get_manager

    manager = get_manager()
    if manager is not None:
        await manager.connect_server(server.id)
    await session.refresh(server)
    counts = await _tool_counts(session, [server.id])
    return _to_out(server, counts.get(server.id, 0))


@router.get("/{server_id}", response_model=McpServerOut)
async def get_server(server_id: UUID, session: SessionDep) -> McpServerOut:
    server = await fetch_or_404(session, McpServer, server_id)
    counts = await _tool_counts(session, [server.id])
    return _to_out(server, counts.get(server.id, 0))


@router.patch("/{server_id}", response_model=McpServerOut)
async def patch_server(server_id: UUID, body: McpServerPatch, session: SessionDep) -> McpServerOut:
    server = await fetch_or_404(session, McpServer, server_id)
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    enforce_static_rules(server, set(changes))
    if "url" in changes and (changes["url"] or server.transport == "http"):
        _check_egress(changes["url"])
    # M52: write-only secrets merge — `***` keeps, null removes, else replaces
    if "env" in changes:
        server.env = merge_secret_map(server.env, changes.pop("env"))
    if "headers" in changes:
        server.headers = merge_secret_map(server.headers, changes.pop("headers"))
    for field, value in changes.items():
        setattr(server, field, value)
    # hardening wave: a connection edit is a different binary behind the
    # same tool rows — hashed onto the row, logged, and reconnected NOW so
    # the swap and its re-ingest happen at edit time, not at the next
    # health ping
    from app.mcp.manager import config_fingerprint, get_manager

    new_hash = config_fingerprint(server)
    # a row never stamped (from before the hash) counts as changed; so does
    # a secret rotation — its VALUE is not in the fingerprint by design, but
    # the running process holds the old one (review round 2)
    # a keep-mask (`***`) entry rewrites nothing — only a new value or a
    # removal is a rotation worth a reconnect (review round 3: a masked
    # round-trip from the form tore a live session down mid-run)
    secrets_written = any(
        value != "***" for value in {**(body.env or {}), **(body.headers or {})}.values()
    )
    config_changed = server.config_hash is None or new_hash != server.config_hash
    server.config_hash = new_hash
    await session.commit()
    # onupdate columns (updated_at) are expired by the flush — reload before
    # serializing, or Pydantic's attribute access triggers lazy IO
    await session.refresh(server)
    if config_changed or secrets_written:
        logger.warning(
            "mcp_server_config_changed",
            server_id=str(server.id),
            name=server.name,
            config_hash=new_hash[:12],
            secrets_rotated=secrets_written and not config_changed,
            changed_fields=sorted(
                set(changes)
                | ({"env"} if body.env is not None else set())
                | ({"headers"} if body.headers is not None else set())
            ),
        )
        manager = get_manager()
        if manager is not None and (server.status != "inactive" or server.config_hash is None):
            await manager.connect_server(server.id)
            await session.refresh(server)
    counts = await _tool_counts(session, [server.id])
    return _to_out(server, counts.get(server.id, 0))


async def _bound_skills(session: SessionDep, server_id: UUID) -> list[Skill]:
    stmt = (
        select(Skill)
        .join(skill_tools, skill_tools.c.skill_id == Skill.id)
        .join(Tool, Tool.id == skill_tools.c.tool_id)
        .where(Tool.mcp_server_id == server_id, Skill.deleted_at.is_(None))
        .distinct()
    )
    return list((await session.execute(stmt)).scalars())


@router.delete("/{server_id}", status_code=204)
async def delete_server(server_id: UUID, session: SessionDep) -> None:
    server = await fetch_or_404(session, McpServer, server_id)
    reject_static_delete(server)
    dependents = await _bound_skills(session, server_id)
    if dependents:
        raise HTTPException(
            status_code=409,
            detail=(
                "server tools are bound to skills: " + ", ".join(sorted(s.name for s in dependents))
            ),
        )
    now = datetime.now(UTC)
    server.deleted_at = now
    for tool in (
        await session.execute(select(Tool).where(Tool.mcp_server_id == server_id))
    ).scalars():
        tool.deleted_at = now
    await session.commit()
    from app.registry_cache import get_cache

    await get_cache().invalidate("tools")
    from app.mcp.manager import get_manager

    manager = get_manager()
    if manager is not None:
        await manager.disconnect_server(server_id)


@router.post("/{server_id}/reconnect", response_model=McpServerOut)
async def reconnect_server(server_id: UUID, session: SessionDep) -> McpServerOut:
    server = await fetch_or_404(session, McpServer, server_id)
    from app.mcp.manager import get_manager

    manager = get_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="MCP manager not running")
    await manager.connect_server(server.id)
    await session.refresh(server)
    counts = await _tool_counts(session, [server.id])
    return _to_out(server, counts.get(server.id, 0))


@router.post("/{server_id}/refresh-tools", response_model=McpServerOut)
async def refresh_tools(server_id: UUID, session: SessionDep) -> McpServerOut:
    server = await fetch_or_404(session, McpServer, server_id)
    from app.mcp.manager import get_manager

    manager = get_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="MCP manager not running")
    await manager.refresh_tools(server.id)
    await session.refresh(server)
    counts = await _tool_counts(session, [server.id])
    return _to_out(server, counts.get(server.id, 0))
