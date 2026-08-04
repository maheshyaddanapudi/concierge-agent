"""MCP connection manager singleton access (spec §5).

M1 ships the seam only: `get_manager()` returns None until the M2 manager is
started at app startup. Routers degrade to 503 for connection actions.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from uuid import UUID


class McpManagerProtocol:
    async def connect_server(self, server_id: "UUID") -> None: ...

    async def disconnect_server(self, server_id: "UUID") -> None: ...

    async def refresh_tools(self, server_id: "UUID") -> None: ...


_manager: McpManagerProtocol | None = None


def get_manager() -> McpManagerProtocol | None:
    return _manager


def set_manager(manager: McpManagerProtocol | None) -> None:
    global _manager
    _manager = manager
