"""mcp_servers registry (spec §3.1)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import RegistryRecord


class McpServer(RegistryRecord):
    __tablename__ = "mcp_servers"

    transport: Mapped[str] = mapped_column(String(16))  # 'stdio' | 'http'
    command: Mapped[str | None] = mapped_column(Text, default=None)
    args: Mapped[list[Any] | None] = mapped_column(default=None)
    env: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    headers: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    # a hash of the connection config (transport, command, args, url, env
    # and header KEYS): a change is a different binary behind the same tool
    # rows, logged and reconnected at once rather than at the next ping
    config_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    # §4: when the OPERATOR switched this server off. `status='inactive'` is
    # overloaded — a freshly registered server is born inactive and the
    # manager flips it to active on its first connect — so the status alone
    # cannot tell "not connected yet" from "a human said stop", which is why
    # the toggle used to be a label: start() and reconcile connected it again
    # every interval. This column is the operator's intent, and it survives a
    # restart. Set on the status→inactive PATCH, cleared on the way back.
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
