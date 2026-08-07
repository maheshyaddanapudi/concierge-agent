"""Idempotent static seed (spec §9).

Upserts match on (source='static', name) — or tool_key for tools — so ids
stay stable across reloads. MCP tool bindings referenced by native skill
documents resolve tolerantly: keys whose tools are not yet ingested (the MCP
manager connects in M2) are re-reconciled on every seed run.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.models import McpServer, Skill, SubAgent, Tool
from app.native.provider import native_sub_agents, native_tools, scan_native
from app.skilldoc import scan_skill_files

SKILLS_DIR = Path(__file__).resolve().parents[1] / "native" / "skills"


async def seed_mcp_servers(session: AsyncSession) -> None:
    config = get_config()
    servers: list[dict[str, Any]] = [
        {
            "name": "fetch",
            "description": "Reference MCP server exposing a fetch tool for web pages.",
            "transport": "stdio",
            "command": "uvx",
            # --with mcp<2: published mcp-server-fetch builds break on mcp 2.x
            "args": ["--with", "mcp<2", "mcp-server-fetch"],
        },
        {
            "name": "filesystem",
            "description": "Reference MCP filesystem server sandboxed to the workspace volume.",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", config.workspace_dir],
        },
    ]
    for data in servers:
        existing = (
            await session.execute(
                select(McpServer).where(
                    McpServer.name == data["name"], McpServer.source == "static"
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(McpServer(**data, source="static", status="inactive"))
        else:
            for field, value in data.items():
                if field != "name":
                    setattr(existing, field, value)
    await session.commit()


async def upsert_native_tools(session: AsyncSession) -> None:
    """Registration scan → tools registry (spec §5b). Entries removed from
    code are marked inactive."""
    scan_native()
    registered = native_tools()
    rows = list(
        (
            await session.execute(
                select(Tool).where(Tool.kind == "native", Tool.source == "static")
            )
        ).scalars()
    )
    by_key = {t.tool_key: t for t in rows}
    for name, entry in registered.items():
        tool = by_key.get(name)
        if tool is None:
            session.add(
                Tool(
                    name=name,
                    description=entry.description,
                    kind="native",
                    source="static",
                    tool_name=name,
                    tool_key=name,
                    native_ref=entry.native_ref,
                    input_schema=entry.input_schema,
                )
            )
        else:
            tool.description = entry.description
            tool.native_ref = entry.native_ref
            tool.input_schema = entry.input_schema
            if tool.status == "inactive":
                tool.status = "active"
    for key, tool in by_key.items():
        if key not in registered:
            tool.status = "inactive"
    await session.commit()


async def seed_native_skills(session: AsyncSession) -> None:
    """.skill.md scan → skills registry (spec §3.3). Tool bindings resolve by
    tool_key; not-yet-ingested MCP tools reconcile on later seed runs."""
    for doc in scan_skill_files(SKILLS_DIR):
        skill = (
            await session.execute(
                select(Skill).where(Skill.name == doc.name, Skill.source == "static")
            )
        ).scalar_one_or_none()
        bound_tools = list(
            (
                await session.execute(
                    select(Tool).where(Tool.tool_key.in_(doc.tools), Tool.deleted_at.is_(None))
                )
            ).scalars()
        )
        if skill is None:
            skill = Skill(
                name=doc.name,
                description=doc.description,
                persona=doc.persona,
                instructions=doc.instructions,
                direct_exposure=doc.direct_exposure,
                max_tool_iterations=doc.max_tool_iterations,
                kind="native",
                source="static",
                tools=bound_tools,
            )
            session.add(skill)
        else:
            skill.description = doc.description
            skill.persona = doc.persona
            skill.instructions = doc.instructions
            skill.max_tool_iterations = doc.max_tool_iterations
            skill.tools = bound_tools
        await session.commit()


async def seed_sub_agents(session: AsyncSession) -> None:
    """research-concierge (spec §9): branch + HITL + both skills."""
    skills = {
        s.name: s
        for s in (await session.execute(select(Skill).where(Skill.source == "static"))).scalars()
    }
    research = skills.get("web-research")
    file_ops = skills.get("file-ops")
    if research is None or file_ops is None:  # pragma: no cover - seed order bug
        raise RuntimeError("native skills must be seeded before sub agents")
    workflow = {
        "nodes": [
            {"id": "research", "type": "skill", "skill_id": str(research.id)},
            {"id": "approve", "type": "hitl", "prompt": "Save findings to a file?"},
            {"id": "write", "type": "skill", "skill_id": str(file_ops.id)},
        ],
        "edges": [
            {"from": "START", "to": "research"},
            {"from": "research", "to": "approve", "condition": "if research found results"},
            {"from": "research", "to": "END", "condition": "if nothing found"},
            {"from": "approve", "to": "write"},
            {"from": "write", "to": "END"},
        ],
    }
    agent = (
        await session.execute(
            select(SubAgent).where(
                SubAgent.name == "research-concierge", SubAgent.source == "static"
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        agent = SubAgent(
            name="research-concierge",
            description=(
                "Researches a topic on the web and, on approval, saves the findings "
                "to a workspace file."
            ),
            persona="You are a helpful research concierge.",
            workflow=workflow,
            kind="custom",
            source="static",
            skills=[research, file_ops],
        )
        session.add(agent)
    else:
        agent.workflow = workflow
        agent.skills = [research, file_ops]
    await session.commit()


async def upsert_native_sub_agents(session: AsyncSession) -> None:
    """Native sub agent cards from the @native_sub_agent scan (spec §3.4)."""
    for name, entry in native_sub_agents().items():
        agent = (
            await session.execute(
                select(SubAgent).where(SubAgent.name == name, SubAgent.source == "static")
            )
        ).scalar_one_or_none()
        if agent is None:
            session.add(
                SubAgent(
                    name=name,
                    description=entry.description,
                    kind="native",
                    source="static",
                    native_ref=entry.native_ref,
                    covers_skill_ids=entry.covers_skill_ids,
                )
            )
        else:
            agent.description = entry.description
            agent.native_ref = entry.native_ref
            agent.covers_skill_ids = entry.covers_skill_ids
    await session.commit()


# First-boot default-model resolution (spec §13): the code default's provider
# may have no key configured. Preference order — flagships per provider.
_FLAGSHIPS: tuple[tuple[str, str], ...] = (
    ("anthropic", "anthropic:claude-sonnet-4-6"),
    ("google_genai", "google_genai:gemini-3.6-flash"),
    ("openai", "openai:gpt-5.6-luna"),
    ("fake", "fake:scripted"),
)


async def resolve_first_boot_default_model(session: AsyncSession) -> str | None:
    """If no explicit default_model has ever been stored and the code
    default's provider is unconfigured, store the first configured
    provider's flagship. An explicit setting is never touched, and with
    nothing configured at all the code default stands (the UI marks it
    unconfigured until a key arrives)."""
    import structlog

    from app.llm import list_providers
    from app.models import AppSetting
    from app.settings_store import DEFAULTS

    if await session.get(AppSetting, "default_model") is not None:
        return None
    default_provider = str(DEFAULTS["default_model"]).split(":", 1)[0]
    providers = {p.provider_id: p for p in list_providers()}
    default_adapter = providers.get(default_provider)
    if default_adapter is not None and default_adapter.is_configured():
        return None
    for provider_id, ref in _FLAGSHIPS:
        adapter = providers.get(provider_id)
        if adapter is not None and adapter.is_configured():
            session.add(AppSetting(key="default_model", value={"value": ref}))
            await session.commit()
            from app.registry_cache import get_cache

            await get_cache().invalidate("settings")
            structlog.get_logger("seed").info(
                "first_boot_default_model",
                resolved=ref,
                reason=f"{default_provider} unconfigured",
            )
            return ref
    return None


async def seed_all(session: AsyncSession) -> dict[str, int]:
    await seed_mcp_servers(session)
    await upsert_native_tools(session)
    await seed_native_skills(session)
    await seed_sub_agents(session)
    await upsert_native_sub_agents(session)
    await resolve_first_boot_default_model(session)
    counts: dict[str, int] = {}
    for label, model in {
        "mcp_servers": McpServer,
        "tools": Tool,
        "skills": Skill,
        "sub_agents": SubAgent,
    }.items():
        rows = (await session.execute(select(model).where(model.deleted_at.is_(None)))).scalars()
        counts[label] = len(list(rows))
    return counts
