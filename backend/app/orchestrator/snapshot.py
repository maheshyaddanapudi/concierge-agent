"""The run's frozen registry snapshot for the modes that resolve live.

Graph mode freezes each plan entry's resolution at dispatch (spec §3.6,
`resolve_node`). Agentic and direct runs used to write nothing: their tools
come from the registry middlewares at each model call, so a trace from
last week referenced whatever the registry holds now. `catalog_snapshot`
pins what the agentic loop could see when the run started — every exposed
tool with its schema version and hash, every exposed skill and sub agent
with the `updated_at` that names its definition — and `write_snapshot`
stores it on the run like the graph-mode snapshot, under `catalog`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import get_session_factory
from app.models import Run


async def catalog_snapshot() -> dict[str, Any]:
    from app.registry_cache import get_cache

    cache = get_cache()
    tools = await cache.tools(exposed_only=True)
    skills = await cache.skills(exposed_only=True)
    agents = await cache.sub_agents()
    return {
        "tools": [
            {
                "id": t["id"],
                "tool_key": t["tool_key"],
                "kind": t["kind"],
                "schema_version": t.get("schema_version"),
                "schema_hash": t.get("schema_hash"),
            }
            for t in tools
        ],
        "skills": [
            {"id": s["id"], "name": s["name"], "updated_at": s.get("updated_at")} for s in skills
        ],
        "sub_agents": [
            {"id": a["id"], "name": a["name"], "updated_at": a.get("updated_at")}
            for a in agents
            if a.get("status") == "active"
        ],
    }


def resolution_snapshot(resolution: Any) -> dict[str, Any]:
    """The same shape graph mode freezes per plan entry: the resolution's
    fields plus its payload (a sub agent's full definition, a tool's schema)."""
    res = dict(resolution.__dict__)
    payload = res.get("payload") or {}
    return (
        {k: v for k, v in res.items() if k != "payload"}
        | {"payload_kinds": sorted(payload.keys())}
        | {"payload": payload}
    )


async def write_snapshot(run_id: UUID, snapshot: dict[str, Any]) -> None:
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is not None:
            run.snapshot = {**(run.snapshot or {}), **snapshot}
            await session.commit()
