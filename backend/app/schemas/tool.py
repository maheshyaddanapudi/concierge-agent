"""Tool schemas (spec §3.2, §4). Tools are never created via API — they come
from MCP ingestion or the native registration scan."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.schemas.common import ApiModel, RegistryOut, Status


class ToolPatch(ApiModel):
    description: str | None = None
    status: Status | None = None
    direct_exposure: bool | None = None
    tool_key: str | None = None
    # 'server' hands an operator-edited description back to the server:
    # the next ingest adopts its wording again (§3.2)
    description_source: Literal["server"] | None = None


class ToolOut(RegistryOut):
    kind: Literal["mcp", "native", "a2a"]
    mcp_server_id: UUID | None
    remote_agent_id: UUID | None
    tool_name: str
    native_ref: str | None
    tool_key: str
    direct_exposure: bool
    input_schema: dict[str, Any] | None
    ingest_state: str | None = None
    # schema fingerprint: the hash and version of input_schema as last
    # ingested; schema_changed_at is set while a change awaits acknowledgement
    schema_hash: str | None = None
    schema_version: int = 1
    schema_changed_at: datetime | None = None
    # description fingerprint (hardening wave): 'server' while the text is
    # whatever the MCP server / A2A card last said; 'operator' once an
    # operator edited it, after which a re-ingest never overwrites it
    description_hash: str | None = None
    description_source: str = "server"
