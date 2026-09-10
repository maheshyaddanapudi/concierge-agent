"""M55 — the fork seam (spec §20, §14r-97..99).

Three layers of proof:

1. **the contract suite** every `AuthProvider` must pass — parametrised over
   every registered provider, the builtin and the reference stub alike,
   the way the model-adapter contract suite runs over every adapter;
2. **the stub end-to-end**: with `AUTH_PROVIDER=stub` the reference stub's
   fake tenancy rule (rows shared by tenant, writes need `editor`) holds
   through the middleware, the work stores and memory recall — with zero
   changes outside `tests/auth_stub.py`;
3. **the seam is real**: no call site outside `app/auth/` decides tenancy
   from the auth switch itself, and the default provider is byte-identical
   to the single-user platform.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import auth
from app.auth import port, registry
from app.config import get_config
from app.models import Conversation, Memory, Run
from tests import auth_stub

ALL_PROVIDERS = registry.list_auth_providers()
PROVIDER_IDS = [p.provider_id for p in ALL_PROVIDERS]
APP_ROOT = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def stub_auth(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("AUTH_PROVIDER", "stub")
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    get_config.cache_clear()
    registry.reset_auth_provider()
    auth_stub.reset()
    yield
    get_config.cache_clear()
    registry.reset_auth_provider()
    auth_stub.reset()


def _as(name: str, tenant: str, role: str = "member") -> dict[str, str]:
    return {"X-Stub-User": name, "X-Stub-Tenant": tenant, "X-Stub-Role": role}


class _Row:
    def __init__(self, user_id: UUID | None) -> None:
        self.user_id = user_id


# ── 1. the contract suite ──────────────────────────────────────────────


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
def test_port_shape(provider: Any) -> None:
    assert isinstance(provider.provider_id, str) and provider.provider_id
    for name in (
        "enabled",
        "identify",
        "owner_id",
        "tenancy_filter",
        "may_see",
        "memory_visibility",
        "authorize",
        "on_boot",
    ):
        assert callable(getattr(provider, name)), name
    assert inspect.iscoroutinefunction(provider.identify)
    assert inspect.iscoroutinefunction(provider.authorize)
    assert inspect.iscoroutinefunction(provider.on_boot)
    assert isinstance(provider, port.AuthProvider)


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_anonymous_principal_is_never_an_owner(provider: Any) -> None:
    assert provider.owner_id(None) is None


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_visibility_is_consistent_between_filter_and_row_check(provider: Any) -> None:
    """A row that passes the provider's SQL tenancy filter must also pass
    its in-memory `may_see`, and vice versa — the two are one rule."""
    principal = port.Principal(id=UUID(int=1), username="p", role="member", tenant="t")
    clause = provider.tenancy_filter(Conversation, principal)
    mine, theirs = _Row(UUID(int=1)), _Row(UUID(int=2))
    if not provider.enabled() and clause is None:
        # single-user: everything is visible and nothing is filtered
        assert provider.may_see(mine, principal) and provider.may_see(theirs, principal)
        return
    assert clause is not None
    # the clause is a SQLAlchemy expression over the model's user_id column
    assert "user_id" in str(clause)
    assert provider.may_see(mine, principal) is True


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_memory_visibility_is_a_fragment_over_the_m_alias(provider: Any) -> None:
    principal = port.Principal(id=UUID(int=3), username="q", role="member", tenant="t")
    frag, params = provider.memory_visibility(principal)
    assert isinstance(frag, str) and isinstance(params, dict)
    if frag:
        assert "m." in frag
        for key in re.findall(r":(\w+)", frag):
            assert key in params or key == "auth_user_id", key
    else:
        assert params == {}


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_reads_are_never_refused_by_authorize(provider: Any) -> None:
    principal = port.Principal(id=UUID(int=4), username="r", role="member", tenant="t")
    assert await provider.authorize(principal, method="GET", path="/api/v1/tools") is None
    assert await provider.authorize(None, method="GET", path="/api/v1/health") is None


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_authorize_returns_a_reason_string_or_none(provider: Any) -> None:
    principal = port.Principal(id=UUID(int=5), username="s", role="member", tenant="t")
    out = await provider.authorize(principal, method="PATCH", path="/api/v1/settings")
    assert out is None or (isinstance(out, str) and out)


@pytest.mark.parametrize("provider", ALL_PROVIDERS, ids=PROVIDER_IDS)
async def test_on_boot_is_idempotent(provider: Any) -> None:
    await provider.on_boot()
    await provider.on_boot()


# ── 2. the registry ────────────────────────────────────────────────────


class TestRegistry:
    def test_builtin_is_the_default_and_the_stub_is_registered(self) -> None:
        assert "builtin" in PROVIDER_IDS and "stub" in PROVIDER_IDS
        registry.reset_auth_provider()
        assert registry.get_auth_provider().provider_id == "builtin"

    def test_unknown_provider_is_refused_at_resolution(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("AUTH_PROVIDER", "nope")
        get_config.cache_clear()
        registry.reset_auth_provider()
        try:
            with pytest.raises(registry.UnknownAuthProviderError):
                registry.get_auth_provider()
        finally:
            get_config.cache_clear()
            registry.reset_auth_provider()

    def test_a_provider_module_is_imported_on_demand(self, monkeypatch: Any) -> None:
        """`AUTH_PROVIDER_MODULE` names the fork's module; the registry
        imports it before resolving, so the decorator inside registers."""
        monkeypatch.setenv("AUTH_PROVIDER", "stub")
        monkeypatch.setenv("AUTH_PROVIDER_MODULE", "tests.auth_stub")
        get_config.cache_clear()
        registry.reset_auth_provider()
        try:
            assert registry.get_auth_provider().provider_id == "stub"
        finally:
            get_config.cache_clear()
            registry.reset_auth_provider()


# ── 3. the stub end-to-end (§14r-97) ───────────────────────────────────


class TestStubEndToEnd:
    async def test_rows_are_shared_by_tenant_and_invisible_across(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        # alice@acme creates a conversation; bob@acme sees it; carol@globex does not
        created = await client.post(
            "/api/v1/conversations", json={"title": "acme roadmap"}, headers=_as("alice", "acme")
        )
        assert created.status_code == 201, created.text
        cid = created.json()["id"]
        async with auth.get_session_factory()() as session:
            row = await session.get(Conversation, UUID(cid))
        assert row is not None and row.user_id == auth_stub.user_id_for("alice")

        bob = await client.get("/api/v1/conversations", headers=_as("bob", "acme"))
        assert [c["id"] for c in bob.json()] == [cid]
        assert (
            await client.get(f"/api/v1/conversations/{cid}", headers=_as("bob", "acme"))
        ).status_code == 200

        carol = await client.get("/api/v1/conversations", headers=_as("carol", "globex"))
        assert carol.status_code == 200 and carol.json() == []
        assert (
            await client.get(f"/api/v1/conversations/{cid}", headers=_as("carol", "globex"))
        ).status_code == 404

    async def test_memory_recall_follows_the_stub_rule(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        await client.patch(
            "/api/v1/settings",
            json={"memory_enabled": True},
            headers=_as("alice", "acme", "editor"),
        )
        made = await client.post(
            "/api/v1/memories",
            json={
                "kind": "fact",
                "text": "the acme roadmap ships pgvector in Q4",
                "scope": "global",
            },
            headers=_as("alice", "acme"),
        )
        assert made.status_code == 201, made.text
        async with auth.get_session_factory()() as session:
            row = await session.get(Memory, UUID(made.json()["id"]))
        assert row is not None and row.user_id == auth_stub.user_id_for("alice")

        bob = await client.get(
            "/api/v1/memories/recall",
            params={"q": "acme roadmap pgvector"},
            headers=_as("bob", "acme"),
        )
        assert bob.status_code == 200 and [h["memory"]["id"] for h in bob.json()] == [
            made.json()["id"]
        ]
        carol = await client.get(
            "/api/v1/memories/recall",
            params={"q": "acme roadmap pgvector"},
            headers=_as("carol", "globex"),
        )
        assert carol.status_code == 200 and carol.json() == []

    async def test_writes_need_the_editor_role_and_reads_do_not(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        denied = await client.patch("/api/v1/settings", json={}, headers=_as("bob", "acme"))
        assert denied.status_code == 403
        assert denied.json()["detail"] == "stub: registry and settings writes need the editor role"
        allowed = await client.patch(
            "/api/v1/settings", json={}, headers=_as("alice", "acme", "editor")
        )
        assert allowed.status_code == 200
        assert (await client.get("/api/v1/settings", headers=_as("bob", "acme"))).status_code == 200

    async def test_no_identity_is_401_and_exempt_paths_stay_open(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        assert (await client.get("/api/v1/tools")).status_code == 401
        assert (await client.get("/health")).status_code == 200

    async def test_the_builtin_login_is_not_offered_by_another_provider(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "x"})
        assert resp.status_code == 404

    async def test_run_ownership_follows_the_provider(
        self, client: AsyncClient, stub_auth: Any
    ) -> None:
        created = await client.post(
            "/api/v1/chat", json={"message": "hello from acme"}, headers=_as("alice", "acme")
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["run_id"]
        async with auth.get_session_factory()() as session:
            run = await session.get(Run, UUID(run_id))
        assert run is not None and run.user_id == auth_stub.user_id_for("alice")
        bob = await client.get(f"/api/v1/runs/{run_id}", headers=_as("bob", "acme"))
        assert bob.status_code == 200
        carol = await client.get(f"/api/v1/runs/{run_id}", headers=_as("carol", "globex"))
        assert carol.status_code == 404

    async def test_streams_ask_the_port_too(self, client: AsyncClient, stub_auth: Any) -> None:
        """The live drill found the run stream serving the whole record to a
        stranger: every SSE surface asks the port like the REST ones."""
        created = await client.post(
            "/api/v1/chat", json={"message": "stream me"}, headers=_as("alice", "acme")
        )
        run_id = created.json()["run_id"]
        await asyncio.sleep(0.5)
        async with client.stream(
            "GET", f"/api/v1/chat/stream/{run_id}", headers=_as("bob", "acme")
        ) as bob:
            assert bob.status_code == 200
        async with client.stream(
            "GET", f"/api/v1/chat/stream/{run_id}", headers=_as("carol", "globex")
        ) as carol:
            assert carol.status_code == 404

    async def test_ambient_stream_delivers_only_what_the_port_admits(
        self, client: AsyncClient, stub_auth: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ambient import channels
        from app.api import ambient as ambient_api
        from app.models import Delivery

        monkeypatch.setattr(channels, "STREAM_KEEPALIVE_S", 0.1)
        # carol@globex subscribes; alice@acme's interrupt and an unowned one are published
        await client.get("/api/v1/settings", headers=_as("carol", "globex"))  # registers carol
        await client.get("/api/v1/settings", headers=_as("alice", "acme"))
        carol = port.Principal(id=auth_stub.user_id_for("carol"), username="carol", tenant="globex")
        auth.set_current_user(carol)
        try:
            gen = ambient_api.ambient_event_stream()
            got: list[dict[str, Any]] = []

            async def collect() -> None:
                async for event in gen:
                    got.append(event)
                    if len([e for e in got if e["event"] == "delivery"]) >= 1:
                        return

            task = asyncio.create_task(collect())
            await asyncio.sleep(0.05)
            channels._publish(
                "interrupt",
                [
                    Delivery(
                        title="acme only",
                        tier=0,
                        urgency=5,
                        category="ops",
                        user_id=auth_stub.user_id_for("alice"),
                    ),
                    Delivery(
                        title="globex too",
                        tier=0,
                        urgency=5,
                        category="ops",
                        user_id=auth_stub.user_id_for("carol"),
                    ),
                ],
            )
            await asyncio.wait_for(task, timeout=3)
            titles = [json.loads(e["data"])["title"] for e in got if e["event"] == "delivery"]
            assert titles == ["globex too"], titles
        finally:
            auth.set_current_user(None)


# ── 4. the seam is real (§14r-98) ──────────────────────────────────────


class TestSeamIsReal:
    def test_no_call_site_outside_the_package_reads_the_auth_switch(self) -> None:
        """Every tenancy decision goes through the port. `auth_enabled()`
        and the config flag are the builtin provider's business only."""
        offenders: list[str] = []
        for path in APP_ROOT.rglob("*.py"):
            if path.is_relative_to(APP_ROOT / "auth"):
                continue
            src = path.read_text()
            if re.search(r"\bauth_enabled\s*\(", src) or "config().auth_enabled" in src:
                offenders.append(str(path.relative_to(APP_ROOT)))
        assert offenders == [], offenders

    def test_the_stub_lives_in_one_module(self) -> None:
        """§14r-97: the reference provider touches nothing outside itself —
        it imports only the port and the registry from the core."""
        src = (Path(__file__).parent / "auth_stub.py").read_text()
        core_imports = re.findall(r"^from app\.(\S+) import", src, flags=re.M)
        assert set(core_imports) <= {"auth.port", "auth.registry"}, core_imports

    async def test_default_provider_is_byte_identical_single_user(
        self, client: AsyncClient, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        monkeypatch.delenv("AUTH_PROVIDER", raising=False)
        get_config.cache_clear()
        registry.reset_auth_provider()
        try:
            provider = registry.get_auth_provider()
            assert provider.provider_id == "builtin" and provider.enabled() is False
            stmt = select(Conversation)
            assert auth.scope_to_user(stmt, Conversation) is stmt
            assert auth.owns_row(_Row(UUID(int=9))) is True
            assert auth.current_user_id() is None
            resp = await client.get("/api/v1/tools")
            assert resp.status_code == 200
            assert "x-frame-options" not in {k.lower() for k in resp.headers}
        finally:
            get_config.cache_clear()
            registry.reset_auth_provider()
