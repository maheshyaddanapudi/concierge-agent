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
    quarantined = policy == "quarantine" and row.status == "active"
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


def acknowledge_schema(row: Tool) -> None:
    """The operator has read the change: clear the flag, and put a
    quarantined row back in service."""
    row.schema_changed_at = None
    if row.ingest_state == QUARANTINED:
        row.ingest_state = "present"
        if row.status == "inactive" and row.deleted_at is None:
            row.status = "active"
