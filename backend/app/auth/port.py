"""The auth seam's port (spec §20, M55): what a fork's authentication and
tenancy layer implements, and nothing else. Mirrors §2.1's provider port —
a Protocol the core codes against, a registry that selects the active
implementation, a contract suite that defines conformance.

No authentication lives here. The builtin provider (`builtin.py`) is
today's §18.8 behaviour; a fork adds one module and points `AUTH_PROVIDER`
at it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from starlette.requests import Request


@dataclass(frozen=True)
class Principal:
    """Who is acting. `id` is the owner stamp for rows (None = anonymous /
    single-user); `role`, `tenant` and `claims` are the provider's to fill
    and to interpret — the core never reads them."""

    id: UUID | None
    role: str = "member"
    username: str | None = None
    tenant: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AuthProvider(Protocol):
    provider_id: str

    def enabled(self) -> bool:
        """False ⇒ the platform is single-user and byte-identical to shipping
        without a provider: no identity, no filters, no headers."""
        ...

    async def identify(self, request: Request) -> Principal | None:
        """Identity resolution. None on a non-exempt API path is a 401."""
        ...

    def owner_id(self, principal: Principal | None) -> UUID | None:
        """The value stamped into `user_id` on rows this principal creates."""
        ...

    def tenancy_filter(self, model: Any, principal: Principal | None) -> Any | None:
        """The SQL predicate per-user work queries add; None ⇒ no filter."""
        ...

    def may_see(self, row: Any, principal: Principal | None) -> bool:
        """The same rule as `tenancy_filter`, for one loaded row."""
        ...

    def memory_visibility(self, principal: Principal | None) -> tuple[str, dict[str, Any]]:
        """The tenancy clause of the memory visibility predicate (§16.3):
        a fragment over the alias `m` plus the parameters it binds, or
        ("", {})."""
        ...

    async def authorize(self, principal: Principal | None, *, method: str, path: str) -> str | None:
        """The authorization decision point: None allows; a reason is a 403."""
        ...

    async def on_boot(self) -> None:
        """Idempotent start-up work (the builtin bootstraps its admin)."""
        ...
