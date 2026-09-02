"""tools registry (spec §3.2)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import RegistryRecord


class Tool(RegistryRecord):
    __tablename__ = "tools"
    # M50 (arch-C2): the server → tools join had no index
    __table_args__ = (Index("tools_mcp_server_idx", "mcp_server_id"),)

    kind: Mapped[str] = mapped_column(String(16))  # 'mcp' | 'native' | 'a2a'
    mcp_server_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mcp_servers.id"), default=None
    )
    remote_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("remote_agents.id"), default=None
    )
    tool_name: Mapped[str] = mapped_column(String(255))
    native_ref: Mapped[str | None] = mapped_column(String(512), default=None)
    tool_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    direct_exposure: Mapped[bool] = mapped_column(Boolean, default=False)
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    # M53: what the SERVER last said about an MCP tool — 'present' | 'missing'
    # — so a re-ingest reactivates only what the server's absence deactivated,
    # never a tool an operator disabled or deleted; None for native/a2a rows
    # and for rows ingested before M53 (treated as operator intent)
    ingest_state: Mapped[str | None] = mapped_column(String(8), default=None)
    # retrieval vector (spec §7.4): maintained best-effort on the write path
    embedding: Mapped[list[Any] | None] = mapped_column(default=None)
    embedding_hash: Mapped[str | None] = mapped_column(String(64), default=None)
