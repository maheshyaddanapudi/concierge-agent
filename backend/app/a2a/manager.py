"""A2A remote-agent manager (spec §19.2/§19.4).

Singleton peer of the MCP manager, simpler by design: A2A is stateless
HTTP, so there are no persistent sessions to hold — per-agent state is
the last fetched Agent Card. Responsibilities: fetch + validate cards,
project ``auth_schemes`` for the UI, ingest card skills into the tools
registry (``kind='a2a'``, MCP ingest semantics: refresh-in-place,
inactive on vanish, collision-suffixed ``tool_key``, cache invalidation),
run the card-refresh loop (interval + master switch re-read live each
cycle), and build authenticated SDK clients for the call path.

The ``a2a`` / ``authlib`` SDKs are imported only inside ``app/a2a/``
(spec §19.1 — the §2.1 isolation discipline applied to A2A).
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import structlog
from a2a.client import A2ACardResolver, Client, ClientConfig, ClientFactory
from a2a.types import AgentCard
from sqlalchemy import select

from app import egress, obs
from app.a2a.auth import AgentCredentialService, ConciergeAuthInterceptor, scheme_supported
from app.db import get_session_factory
from app.models import RemoteAgent, Tool
from app.toolschema import (
    AGENT_INACTIVE,
    apply_description,
    apply_schema,
    definition_fingerprint,
    schema_fingerprint,
    text_fingerprint,
)

logger = structlog.get_logger("a2a")

CARD_FETCH_TIMEOUT_S = 15.0
DEFAULT_CARD_PATH = "/.well-known/agent-card.json"
_DARK_SLEEP_S = 30.0

# the fixed invocation surface of every projected a2a tool (spec §19.4):
# A2A skills are advisory — invocation is agent-level message/send
A2A_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The task or question to send to the remote agent, in plain language.",
        },
        "data": {
            "type": "object",
            "description": "Optional structured data to attach to the message.",
        },
    },
    "required": ["message"],
}


def split_card_url(card_url: str) -> tuple[str, str]:
    """A registered URL may be a base URL or the full card path."""
    parts = urlsplit(card_url)
    base = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or ""
    if path.endswith(".json"):
        return base, path
    return f"{base}{path.rstrip('/')}", DEFAULT_CARD_PATH


def project_auth_schemes(card: AgentCard) -> dict[str, Any]:
    """UI projection of the card's securitySchemes (spec §19.3)."""
    out: dict[str, Any] = {}
    for name, wrapper in (card.security_schemes or {}).items():
        scheme_def = wrapper.root
        out[name] = {
            "type": getattr(scheme_def, "type", "unknown"),
            "supported": scheme_supported(scheme_def),
        }
    return out


def skill_description(skill: Any) -> str:
    """Planner routing signal: name + description + tags digest (§19.4)."""
    parts = [f"{skill.name}: {skill.description}".strip().rstrip(":").strip()]
    if skill.tags:
        parts.append(f"[tags: {', '.join(skill.tags)}]")
    return " ".join(p for p in parts if p)


class A2AManager:
    def __init__(self) -> None:
        # M52: card fetches and A2A calls go through the egress policy —
        # every request, every redirect hop
        self._http = egress.client(timeout=CARD_FETCH_TIMEOUT_S)
        self._refresh_task: asyncio.Task[None] | None = None

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Refresh every persisted agent (when a2a is on) + refresh loop."""
        # M40: `a2a_http_timeout_s` is applied on the manager's next client
        # build (this start) — __init__ keeps the code default for tests
        # that never start the manager
        try:
            from app.registry_cache import get_cache

            timeout_s = max(float(await get_cache().setting("a2a_http_timeout_s")), 1.0)
        except Exception:  # noqa: BLE001 — settings hiccup keeps the default client
            timeout_s = CARD_FETCH_TIMEOUT_S
        if timeout_s != CARD_FETCH_TIMEOUT_S:
            old = self._http
            self._http = egress.client(timeout=timeout_s)
            await old.aclose()
        if await self._enabled():
            async with get_session_factory()() as db:
                agent_ids = list(
                    (
                        await db.execute(
                            select(RemoteAgent.id).where(RemoteAgent.deleted_at.is_(None))
                        )
                    ).scalars()
                )
            await asyncio.gather(
                *(self.refresh_agent(aid) for aid in agent_ids), return_exceptions=True
            )
        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
            self._refresh_task = None
        await self._http.aclose()

    async def _enabled(self) -> bool:
        from app.registry_cache import get_cache

        return bool(await get_cache().setting("a2a_enabled"))

    # ── card fetch + ingest (spec §19.2/§19.4) ───────────────────

    async def fetch_card(self, card_url: str) -> AgentCard:
        base, path = split_card_url(card_url)
        resolver = A2ACardResolver(self._http, base, agent_card_path=path)
        return await resolver.get_agent_card()

    async def refresh_agent(self, agent_id: UUID, *, activate: bool = False) -> None:
        """(Re)fetch the card, project schemes, ingest skills, set status.
        `activate` is registration's first fetch: the row is born inactive
        and a good card makes it active; every later fetch recovers an
        ERROR agent only — an operator's `inactive` is theirs to undo."""
        async with get_session_factory()() as db:
            agent = await db.get(RemoteAgent, agent_id)
            if agent is None or agent.deleted_at is not None:
                return
            card_url = agent.card_url
            secrets = _credential_strings(agent.credentials)
        try:
            card = await self.fetch_card(card_url)
        except BaseException as exc:  # noqa: BLE001 - recorded on the row
            await self._record_status(agent_id, "error", error=_describe(exc, secrets=secrets))
            logger.warning(
                "a2a_card_fetch_failed",
                tier="a2a",
                kind="card_fetch",
                agent_id=str(agent_id),
                error=_describe(exc),
            )
            return
        async with get_session_factory()() as db:
            agent = await db.get(RemoteAgent, agent_id)
            if agent is None or agent.deleted_at is not None:
                return
            dumped = card.model_dump(mode="json", by_alias=True, exclude_none=True)
            # hardening wave: a card that changed under a refresh (endpoint,
            # schemes, skills, anything) is versioned, logged and counted —
            # the client built from it moves with it, never silently
            new_hash = definition_fingerprint(dumped)
            if agent.card_hash is not None and new_hash != agent.card_hash:
                previous = agent.card or {}
                changed_keys = sorted(
                    k for k in set(previous) | set(dumped) if previous.get(k) != dumped.get(k)
                )
                agent.card_version = int(agent.card_version or 1) + 1
                obs.A2A_CARD_CHANGES.inc()
                logger.warning(
                    "a2a_card_changed",
                    tier="a2a",
                    kind="card_fetch",
                    agent_id=str(agent_id),
                    card_version=agent.card_version,
                    changed_keys=changed_keys,
                    previous_hash=agent.card_hash[:12],
                    card_hash=new_hash[:12],
                )
            agent.card_hash = new_hash
            agent.card = dumped
            agent.card_fetched_at = datetime.now(UTC)
            agent.auth_schemes = project_auth_schemes(card)
            # a fetch recovers an ERROR agent; an operator's `inactive` is
            # theirs alone to undo (review round 2 — a refresh used to
            # re-enable a disabled agent within one interval)
            if agent.status == "error" or (activate and agent.status == "inactive"):
                agent.status = "active"
            agent.last_error = None
            await db.commit()
        await self._ingest(agent_id, card)
        logger.info(
            "a2a_card_refreshed",
            tier="a2a",
            kind="card_fetch",
            agent_id=str(agent_id),
            skills=len(card.skills),
        )

    async def _ingest(self, agent_id: UUID, card: AgentCard) -> None:
        """Project card skills into the tools registry (MCP _ingest semantics)."""
        async with get_session_factory()() as db:
            agent = await db.get(RemoteAgent, agent_id)
            if agent is None:
                return
            existing = {
                t.tool_name: t
                for t in (
                    await db.execute(select(Tool).where(Tool.remote_agent_id == agent_id))
                ).scalars()
            }
            taken_keys = set((await db.execute(select(Tool.tool_key))).scalars())
            # the LLM-facing name is the sanitized key: a new key that
            # sanitizes like an existing one would bind first-wins and
            # silently lose (the MCP ingest rule, mirrored — review round 2)
            from app.factory.worker import sanitize_tool_name

            taken_names = {sanitize_tool_name(k) for k in taken_keys}
            seen: set[str] = set()
            changed_ids: list[str] = []
            for skill in card.skills:
                seen.add(skill.id)
                row = existing.get(skill.id)
                if row is None:
                    key = f"{agent.name}.{skill.name}"
                    if key in taken_keys or sanitize_tool_name(key) in taken_names:
                        key = f"{key}-{uuid4().hex[:6]}"  # collision-safe (spec §3.2)
                    taken_keys.add(key)
                    taken_names.add(sanitize_tool_name(key))
                    db.add(
                        Tool(
                            name=skill.name,
                            description=skill_description(skill),
                            kind="a2a",
                            source=agent.source,  # inherited (spec §19.4)
                            status="active",
                            remote_agent_id=agent_id,
                            tool_name=skill.id,
                            tool_key=key,
                            input_schema=A2A_TOOL_INPUT_SCHEMA,
                            schema_hash=schema_fingerprint(A2A_TOOL_INPUT_SCHEMA),
                            schema_version=1,
                            description_hash=text_fingerprint(skill_description(skill)),
                            ingest_state="present",
                        )
                    )
                else:
                    # MCP ingest_state semantics (M53) apply here too: only
                    # the CARD's absence is undone by the skill's return —
                    # an operator's disable or delete stays as set, and a
                    # rewritten description is a logged change
                    if apply_description(row, skill_description(skill), source="server"):
                        changed_ids.append(str(row.id))
                    apply_schema(row, A2A_TOOL_INPUT_SCHEMA, policy="warn")
                    if row.ingest_state == "missing" and row.deleted_at is None:
                        row.status = "active"
                    if row.ingest_state != AGENT_INACTIVE:  # the agent's re-enable undoes that
                        row.ingest_state = "present"
            for skill_id, row in existing.items():
                if skill_id not in seen:
                    if row.status == "active":
                        row.status = "inactive"  # removed skills marked inactive
                        row.ingest_state = "missing"
                    elif row.ingest_state == "present":
                        row.ingest_state = None
            await db.commit()
        from app.retrieval import schedule_embedding

        for tool_id in changed_ids:
            schedule_embedding("tools", tool_id)
        from app.registry_cache import get_cache

        await get_cache().invalidate("tools")
        logger.info(
            "a2a_skills_ingested",
            tier="a2a",
            kind="ingest",
            agent_id=str(agent_id),
            skill_count=len(card.skills),
        )

    async def _refresh_loop(self) -> None:
        from app.registry_cache import get_cache

        while True:
            try:
                if not await self._enabled():
                    await asyncio.sleep(_DARK_SLEEP_S)
                    continue
                interval = int(await get_cache().setting("a2a_card_refresh_interval_s"))
            except Exception:  # noqa: BLE001 — cache not up yet: stay quiet, retry
                await asyncio.sleep(_DARK_SLEEP_S)
                continue
            await asyncio.sleep(max(interval, 5))
            with contextlib.suppress(Exception):
                if not await self._enabled():
                    continue
                async with get_session_factory()() as db:
                    agent_ids = list(
                        (
                            await db.execute(
                                select(RemoteAgent.id).where(
                                    RemoteAgent.deleted_at.is_(None),
                                    RemoteAgent.status != "inactive",  # disabled: left alone
                                )
                            )
                        ).scalars()
                    )
                for aid in agent_ids:
                    await self.refresh_agent(aid)

    # ── call path (spec §19.5 — consumed by the M38 proxy) ───────

    async def build_client(self, agent_id: UUID) -> tuple[Client, AgentCard]:
        """An authenticated SDK client for one registered agent."""
        async with get_session_factory()() as db:
            agent = await db.get(RemoteAgent, agent_id)
            if agent is None or agent.deleted_at is not None or agent.card is None:
                raise RuntimeError(f"remote agent {agent_id} is not registered")
            if agent.status == "inactive":
                # the operator's disable is enforced at the call, not only
                # shown on the page (review round 2)
                raise RuntimeError(f"remote agent {agent.name!r} is disabled (status inactive)")
            card = AgentCard.model_validate(agent.card)
            credentials = dict(agent.credentials or {})
        service = AgentCredentialService(agent_id=str(agent_id), card=card, credentials=credentials)
        # streaming preferred; the factory falls back to blocking message/send
        # for cards that don't declare streaming (polling=False — that flag
        # would force blocking sends and starve early task events, §19.6)
        config = ClientConfig(streaming=True, polling=False, httpx_client=self._http)
        client = ClientFactory(config).create(
            card, interceptors=[ConciergeAuthInterceptor(service)]
        )
        return client, card

    # ── helpers ──────────────────────────────────────────────────

    async def _record_status(self, agent_id: UUID, status: str, error: str | None = None) -> None:
        async with get_session_factory()() as db:
            agent = await db.get(RemoteAgent, agent_id)
            if agent is None:
                return
            agent.status = status
            agent.last_error = error
            await db.commit()


def _credential_strings(credentials: dict[str, Any] | None) -> list[str]:
    """The agent's own secrets, resolved, for the sanitizer (M52)."""
    from app.a2a.auth import resolve_credential_value

    out: list[str] = []
    for value in (credentials or {}).values():
        resolved = resolve_credential_value(value)
        if isinstance(resolved, dict):
            out.extend(str(v) for v in resolved.values() if v)
        elif resolved:
            out.append(str(resolved))
    return out


def _describe(exc: BaseException, *, secrets: list[str] | None = None) -> str:
    """Error text for the row — through the one sanitizer (M52), with the
    record's own credentials as extra secrets."""
    from app.sanitize import sanitize_error

    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return "card fetch timed out"
    if isinstance(exc, BaseExceptionGroup):
        parts = [_describe(e, secrets=secrets) for e in exc.exceptions]
        return "; ".join(dict.fromkeys(parts))
    raw = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return sanitize_error(raw, extra_secrets=secrets or ()) or raw


_manager: A2AManager | None = None


def get_manager() -> A2AManager | None:
    return _manager


def set_manager(manager: A2AManager | None) -> None:
    global _manager
    _manager = manager
