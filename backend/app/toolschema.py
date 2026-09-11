"""Tool schema fingerprints (spec §3.2 drift).

A tool's input schema is server-owned and changes without a deploy: an MCP
server renames a parameter, re-ingests, and every skill whose instructions
named the old parameter now calls the tool wrong — with nothing in the
registry or the run record to say so. Every write of `input_schema` goes
through `apply_schema`, which fingerprints the schema, versions it, and on
a change logs, counts and flags the row (warn) or also takes it out of
service until an operator acknowledges it (quarantine). The version and
hash ride on every tool_call step, so a trace pins the schema it ran
against.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from app import obs
from app.models import Tool

logger = structlog.get_logger("toolschema")

SCHEMA_CHANGE_POLICIES = {"warn", "quarantine"}
# `ingest_state` value for a tool the quarantine policy took out of service
# on a schema change: a re-ingest must not reactivate it (only the operator's
# acknowledgement does), unlike a 'missing' tool the server merely dropped
QUARANTINED = "changed"
# an A2A tool taken out of service because its remote agent was disabled
# (review round 3): brought back by the agent's re-enable, never by a
# card refresh — `ingest_state` is 8 characters wide
AGENT_INACTIVE = "agentoff"


def schema_fingerprint(schema: dict[str, Any] | None) -> str | None:
    """A stable content hash of a JSON schema: key order and whitespace do
    not count as changes, anything else does."""
    if schema is None:
        return None
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def apply_schema(
    row: Tool,
    schema: dict[str, Any] | None,
    *,
    policy: str = "warn",
    now: datetime | None = None,
) -> bool:
    """Write `schema` onto the row with its fingerprint. Returns whether
    this was a CHANGE (a different schema than the one the row already
    carried): the version is bumped, the change is logged and counted, the
    row is flagged for acknowledgement, and under `quarantine` an active
    row goes inactive with `ingest_state='changed'`. A first sighting (no
    stored hash — a new row, or a row from before fingerprints existed)
    records the hash without flagging."""
    new_hash = schema_fingerprint(schema)
    old_hash = row.schema_hash
    row.input_schema = schema
    if old_hash is None or new_hash == old_hash:
        row.schema_hash = new_hash
        if row.schema_version is None:  # a row built in memory before the default applies
            row.schema_version = 1
        return False
    row.schema_hash = new_hash
    row.schema_version = int(row.schema_version or 1) + 1
    row.schema_changed_at = now or datetime.now(UTC)
    # an active row, or one the server is bringing back from `missing`
    # (review round 3: a tool that vanished and returned with a renamed
    # parameter used to be reactivated at once, past the policy)
    quarantined = policy == "quarantine" and (
        row.status == "active" or (row.ingest_state == "missing" and row.deleted_at is None)
    )
    if quarantined:
        row.status = "inactive"
        row.ingest_state = QUARANTINED
    obs.TOOL_SCHEMA_CHANGES.labels(kind=row.kind, policy=policy).inc()
    logger.warning(
        "tool_schema_changed",
        tool_id=str(row.id),
        tool_key=row.tool_key,
        kind=row.kind,
        schema_version=row.schema_version,
        previous_hash=old_hash[:12],
        schema_hash=new_hash[:12] if new_hash else None,
        policy=policy,
        quarantined=quarantined,
    )
    return True


def text_fingerprint(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def apply_description(row: Tool, text: str, *, source: str = "server") -> bool:
    """Write a tool description the way `apply_schema` writes a schema: the
    planner and retrieval route by description, so a server rewording it
    is a change worth a log line and a counter, not a silent overwrite. An
    operator's own edit (`description_source='operator'`) is never
    overwritten by a re-ingest — only by the operator. Returns whether the
    stored description changed."""
    new_hash = text_fingerprint(text)
    if source == "server" and row.description_source == "operator":
        if new_hash != text_fingerprint(row.description):
            # the server reworded a tool whose wording the operator owns:
            # not applied, but never invisible (review round 2)
            logger.info(
                "tool_description_change_suppressed",
                tool_id=str(row.id),
                tool_key=row.tool_key,
                server_hash=(new_hash or "")[:12],
            )
        return False
    old_hash = row.description_hash
    changed = old_hash is not None and new_hash != old_hash
    row.description = text
    row.description_hash = new_hash
    row.description_source = source
    if changed:
        obs.TOOL_DESCRIPTION_CHANGES.labels(kind=row.kind, source=source).inc()
        logger.warning(
            "tool_description_changed",
            tool_id=str(row.id),
            tool_key=row.tool_key,
            kind=row.kind,
            previous_hash=(old_hash or "")[:12],
            description_hash=(new_hash or "")[:12],
            source=source,
        )
    return changed


def definition_fingerprint(fields: dict[str, Any]) -> str:
    """A stable hash of a definition (a skill's, a sub agent's, a card's):
    the fields that change what the thing DOES, never its status or
    exposure, so a toggle is not a new version."""
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stamp_definition(row: Any, fields: dict[str, Any]) -> bool:
    """Set `definition_hash` / bump `definition_version` on a skill or sub
    agent row from its definition fields. Returns whether the definition
    changed (a first stamp is not a change)."""
    new_hash = definition_fingerprint(fields)
    old_hash = getattr(row, "definition_hash", None)
    if old_hash == new_hash:
        return False
    row.definition_hash = new_hash
    if old_hash is None:
        if getattr(row, "definition_version", None) is None:
            row.definition_version = 1
        return False
    row.definition_version = int(row.definition_version or 1) + 1
    return True


def skill_definition_fields(
    *,
    description: str,
    persona: str,
    instructions: str,
    model: str | None,
    model_params: dict[str, Any] | None,
    max_tool_iterations: int | None,
    tool_ids: list[Any],
) -> dict[str, Any]:
    return {
        "description": description,
        "persona": persona,
        "instructions": instructions,
        "model": model,
        "model_params": model_params,
        "max_tool_iterations": max_tool_iterations,
        "tool_ids": sorted(str(t) for t in tool_ids),
    }


def sub_agent_definition_fields(
    *,
    description: str,
    persona: str,
    model: str | None,
    model_params: dict[str, Any] | None,
    workflow: dict[str, Any] | None,
    native_ref: str | None,
) -> dict[str, Any]:
    return {
        "description": description,
        "persona": persona,
        "model": model,
        "model_params": model_params,
        "workflow": workflow,
        "native_ref": native_ref,
    }


def acknowledge_schema(row: Tool) -> None:
    """The operator has read the change: clear the flag, and put a
    quarantined row back in service."""
    row.schema_changed_at = None
    if row.ingest_state == QUARANTINED:
        row.ingest_state = "present"
        if row.status == "inactive" and row.deleted_at is None:
            row.status = "active"
