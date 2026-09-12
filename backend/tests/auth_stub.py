"""The reference stub `AuthProvider` (spec §20, M55) — a fork's auth layer
written as ONE module against `docs/extending.md`, registered by the
decorator, selected by `AUTH_PROVIDER=stub`. Nothing outside this file
knows it exists; the seam test proves its rule holds end-to-end anyway.

The fake rule it enforces, deliberately unlike the builtin's:

- identity comes from headers — `X-Stub-User` names the principal (id is
  a uuid5 of the name, so it is stable), `X-Stub-Tenant` names the tenant,
  `X-Stub-Role` is `member` unless `editor`;
- **rows are shared by tenant**: every principal sees the rows owned by
  anyone in the same tenant (the builtin shows a user only its own);
- registry and settings writes need the `editor` role (the builtin says
  `admin`).
"""

from __future__ import annotations

import uuid
from typing import Any

from starlette.requests import Request

from app.auth.port import Principal
from app.auth.registry import auth_provider

NAMESPACE = uuid.UUID("6f1d2a3b-4c5d-4e6f-8a9b-0c1d2e3f4a5b")
_WRITE_PREFIXES = ("/api/v1/mcp-servers", "/api/v1/tools", "/api/v1/skills", "/api/v1/settings")

# who belongs to which tenant — learned as principals show up, so the rule
# can be exercised without a schema of its own
_tenants: dict[uuid.UUID, str] = {}


def user_id_for(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


def reset() -> None:
    _tenants.clear()


def _visible_ids(principal: Principal) -> list[uuid.UUID]:
    """The principal's own id plus everyone recorded in its tenant."""
    ids = [uid for uid, t in _tenants.items() if t == principal.tenant]
    if principal.id is not None and principal.id not in ids:
        ids.append(principal.id)
    return ids


@auth_provider
class StubAuthProvider:
    provider_id = "stub"

    def enabled(self) -> bool:
        return True

    async def identify(self, request: Request) -> Principal | None:
        name = request.headers.get("x-stub-user")
        if not name:
            return None
        tenant = request.headers.get("x-stub-tenant") or "default"
        uid = user_id_for(name)
        _tenants[uid] = tenant
        role = "editor" if request.headers.get("x-stub-role") == "editor" else "member"
        return Principal(id=uid, username=name, role=role, tenant=tenant)

    def owner_id(self, principal: Principal | None) -> uuid.UUID | None:
        return principal.id if principal is not None else None

    def tenancy_filter(self, model: Any, principal: Principal | None) -> Any | None:
        if principal is None:
            return model.user_id.is_(None)
        return model.user_id.in_(_visible_ids(principal))

    def may_see(self, row: Any, principal: Principal | None) -> bool:
        owner = getattr(row, "user_id", None)
        if principal is None:
            return owner is None
        return owner in _visible_ids(principal)

    def memory_visibility(self, principal: Principal | None) -> tuple[str, dict[str, Any]]:
        if principal is None:
            return "m.user_id IS NULL", {}
        ids = [str(u) for u in _visible_ids(principal)]
        return "m.user_id = ANY(CAST(:stub_tenant_ids AS uuid[]))", {"stub_tenant_ids": ids}

    async def authorize(self, principal: Principal | None, *, method: str, path: str) -> str | None:
        is_write = method in {"POST", "PATCH", "PUT", "DELETE"} and path.startswith(_WRITE_PREFIXES)
        if is_write and (principal is None or principal.role != "editor"):
            return "stub: registry and settings writes need the editor role"
        return None

    async def on_boot(self) -> None:
        return None
