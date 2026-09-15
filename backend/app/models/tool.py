"""tools registry (spec §3.2)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import RegistryRecord


class Tool(RegistryRecord):
    __tablename__ = "tools"
    # M50 (arch-C2): the server → tools join had no index; M54 (scale-H6): one
    # row per (server, tool name) is a database fact, so N replicas ingesting
    # the same server at once upsert instead of racing a unique violation
    __table_args__ = (
        Index("tools_mcp_server_idx", "mcp_server_id"),
        Index(
            "tools_server_tool_uq",
            "mcp_server_id",
            "tool_name",
            unique=True,
            postgresql_where=text("mcp_server_id IS NOT NULL"),
        ),
        # the same database fact for the A2A projection: two card refreshes
        # for one agent overlapping (a manual refresh landing on the periodic
        # one) both read an empty `existing` and both inserted the skill, so
        # the agent ended up with duplicate tools and no way to tell them
        # apart. One row per (agent, skill id), upserted.
        Index(
            "tools_agent_skill_uq",
            "remote_agent_id",
            "tool_name",
            unique=True,
            postgresql_where=text("remote_agent_id IS NOT NULL"),
        ),
        # `tool_key` is unique among LIVE rows only. It used to be unique
        # across every row ever written, tombstones included, which made a
        # soft delete reserve its key forever: delete an MCP server and
        # register it again under the same name and the ingest found
        # `sitefiles.echo` taken by a row no API or page will show, so it fell
        # to the collision suffix and wrote `sitefiles.echo-88501d`. §4 gives
        # the suffix one job — keeping two SERVERS that expose the same tool
        # name apart — not disambiguating a server from its own deleted past,
        # and §14 step 2 promises plain `{server}.{tool}` keys. The operator
        # saw neither the tombstone nor a reason for the mangled key.
        #
        # A partial index is what lets the key be reused, so the ingest probe
        # in mcp/manager.py filters to live rows to match. The pair has to
        # move together: scoping only the probe trades a mangled key for an
        # IntegrityError, and scoping only the index leaves the suffix.
        Index(
            "ix_tools_tool_key",
            "tool_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(16))  # 'mcp' | 'native' | 'a2a'
    mcp_server_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mcp_servers.id"), default=None
    )
    remote_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("remote_agents.id"), default=None
    )
    tool_name: Mapped[str] = mapped_column(String(255))
    native_ref: Mapped[str | None] = mapped_column(String(512), default=None)
    # uniqueness and the index both live in __table_args__ above, as a
    # partial (live-rows-only) unique index — `unique=True, index=True` here
    # would additionally emit the unconditional one this replaces
    tool_key: Mapped[str] = mapped_column(String(255))
    direct_exposure: Mapped[bool] = mapped_column(Boolean, default=False)
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    # M53: what the SERVER last said about an MCP tool — 'present' | 'missing'
    # — so a re-ingest reactivates only what the server's absence deactivated,
    # never a tool an operator disabled or deleted; None for native/a2a rows
    # and for rows ingested before M53 (treated as operator intent)
    ingest_state: Mapped[str | None] = mapped_column(String(8), default=None)
    # schema fingerprint (spec §3.2 drift): a content hash of `input_schema`
    # as last written, the version that hash is (1 at first sighting, +1 on
    # every change) and, while a change awaits the operator's acknowledgement,
    # when it was noticed — a renamed parameter is loud, never silent
    schema_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    schema_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # the description is what the planner routes by: fingerprinted like the
    # schema, and an operator's edit ('operator') survives re-ingests
    description_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    description_source: Mapped[str] = mapped_column(
        String(16), default="server", server_default="server"
    )
    # retrieval vector (spec §7.4): maintained best-effort on the write path
    embedding: Mapped[list[Any] | None] = mapped_column(default=None)
    # Text, not String(64): the migration created it as TEXT and skills
    # already declare it that way — the model is what drifted
    embedding_hash: Mapped[str | None] = mapped_column(Text, default=None)
