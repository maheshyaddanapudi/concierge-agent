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
            {
                "id": s["id"],
                "name": s["name"],
                "definition_version": s.get("definition_version"),
                "definition_hash": s.get("definition_hash"),
            }
            for s in skills
        ],
        "sub_agents": [
            {
                "id": a["id"],
                "name": a["name"],
                "definition_version": a.get("definition_version"),
                "definition_hash": a.get("definition_hash"),
            }
            for a in agents
            if a.get("status") == "active"
        ],
    }


def prompt_hashes() -> dict[str, str]:
    """A short hash per prompt file: the largest unversioned input to a
    run, pinned on the snapshot so a deploy that edits a prompt is visible
    in the record rather than read as model nondeterminism."""
    import hashlib
    from pathlib import Path

    from app.prompts import load_prompt

    prompts_dir = Path(load_prompt.__wrapped__.__code__.co_filename).resolve().parent
    out: dict[str, str] = {}
    for path in sorted(prompts_dir.glob("*.md")):
        out[path.stem] = hashlib.sha256(load_prompt(path.stem).encode("utf-8")).hexdigest()[:12]
    return out


def run_settings_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    """The settings that shaped the run, as the run saw them (a run reads
    some knobs live per step, but the snapshot at start is the operator's
    baseline). No provider keys live in settings (spec §3.7)."""
    import os

    return {
        "settings": dict(settings),
        "prompts": prompt_hashes(),
        "build": os.environ.get("APP_BUILD") or None,
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


async def pinned_resolution(run_id: UUID, entry_id: str) -> Any | None:
    """The Resolution a run froze under `entry_id`, rebuilt from the
    snapshot — what a HITL replay executes (spec §3.6)."""
    from app.orchestrator.ladder import Resolution

    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        entry = ((run.snapshot or {}) if run is not None else {}).get(entry_id)
    if not isinstance(entry, dict) or "rung" not in entry:
        return None
    entity_id = entry.get("entity_id")
    return Resolution(
        rung=str(entry.get("rung")),
        tier=str(entry.get("tier") or ""),
        kind=str(entry.get("kind") or ""),
        source=str(entry.get("source") or ""),
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_name=str(entry.get("entity_name") or ""),
        payload=dict(entry.get("payload") or {}),
        definition_version=entry.get("definition_version"),
        definition_hash=entry.get("definition_hash"),
    )


async def frozen_definition_hash(run_id: UUID, kind: str, record_id: str) -> str | None:
    """The hash the run's frozen catalog holds for one record, or None."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        catalog = ((run.snapshot or {}) if run is not None else {}).get("catalog") or {}
    for rec in catalog.get(kind) or []:
        if isinstance(rec, dict) and str(rec.get("id")) == str(record_id):
            value = rec.get("definition_hash") or rec.get("schema_hash")
            return str(value) if value else None
    return None


# the top-level keys the run's pins live under — a plan entry id may not
# be one of them (validate_plan refuses it): `direct` is the direct-mode
# entry, `exemplar_vote` the deferred reuse vote (memory/procedural.py)
RESERVED_SNAPSHOT_KEYS = frozenset(
    {
        "settings",
        "prompts",
        "build",
        "context",
        "catalog_calls",
        "catalog",
        "resumes",
        "direct",
        "exemplar_vote",
    }
)


async def write_snapshot(run_id: UUID, snapshot: dict[str, Any]) -> None:
    """Merge `snapshot` onto the run's (top-level keys replace). The row is
    locked for the read-modify-write: two writers interleaving on the
    JSON column would otherwise drop one merge (review round 3 — no
    concurrent writer exists inside one run today; the lock keeps it so)."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id, with_for_update=True)
        if run is not None:
            run.snapshot = {**(run.snapshot or {}), **snapshot}
            await session.commit()


async def append_snapshot_list(run_id: UUID, key: str, *items: Any, cap: int = 200) -> None:
    """Append to a list-valued snapshot key (context, catalog_calls,
    resumes): a HITL resume's fresh context lands next to the pre-pause
    half's, never over it. Bounded by `cap` entries, oldest kept."""
    if not items:
        return
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id, with_for_update=True)
        if run is not None:
            current = (run.snapshot or {}).get(key)
            existing = list(current) if isinstance(current, list) else []
            room = max(cap - len(existing), 0)
            run.snapshot = {**(run.snapshot or {}), key: existing + list(items)[:room]}
            await session.commit()
