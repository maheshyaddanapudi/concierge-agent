"""The builtin `AuthProvider` (spec §20, M55): today's §18.8 behaviour
behind the port — dark unless `AUTH_ENABLED`, then hashed bearer sessions,
per-user rows, the `admin` gate on registry and settings writes, and the
bootstrap admin at boot. Registered like any other provider; passes the
same contract suite."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from starlette.requests import Request

from app.auth.port import Principal
from app.auth.registry import auth_provider

_ADMIN_WRITE = re.compile(r"^/api/v1/(mcp-servers|remote-agents|tools|skills|sub-agents|settings)")


@auth_provider
class BuiltinAuthProvider:
    provider_id = "builtin"

    def enabled(self) -> bool:
        from app.config import get_config

        return bool(get_config().auth_enabled)

    async def identify(self, request: Request) -> Principal | None:
        from app.auth import authenticate

        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not token:
            # EventSource cannot set headers — SSE endpoints accept the
            # session token as a query param (still hashed-at-rest, TTL'd)
            token = str(request.query_params.get("token") or "")
        user = await authenticate(token)
        if user is None:
            return None
        return Principal(
            id=UUID(str(user["id"])),
            role=str(user.get("role") or "member"),
            username=user.get("username"),
            claims={"prefs": user.get("prefs") or {}},
        )

    def owner_id(self, principal: Principal | None) -> UUID | None:
        return principal.id if principal is not None else None

    def tenancy_filter(self, model: Any, principal: Principal | None) -> Any | None:
        if not self.enabled():
            return None
        return model.user_id == (principal.id if principal is not None else None)

    def may_see(self, row: Any, principal: Principal | None) -> bool:
        if not self.enabled():
            return True
        return getattr(row, "user_id", None) == (principal.id if principal is not None else None)

    def memory_visibility(self, principal: Principal | None) -> tuple[str, dict[str, Any]]:
        if not self.enabled():
            return "", {}
        uid = str(principal.id) if principal is not None and principal.id is not None else None
        return "(m.user_id = CAST(:auth_user_id AS uuid) OR m.user_id IS NULL)", {
            "auth_user_id": uid
        }

    async def authorize(self, principal: Principal | None, *, method: str, path: str) -> str | None:
        if (
            method in {"POST", "PATCH", "PUT", "DELETE"}
            and _ADMIN_WRITE.match(path)
            and "/invoke" not in path
            and "/overlap" not in path
            and (principal is None or principal.role != "admin")
        ):
            return "registry and settings writes require the admin role"
        return None

    async def on_boot(self) -> None:
        if self.enabled():
            from app.auth import bootstrap_admin

            await bootstrap_admin()
