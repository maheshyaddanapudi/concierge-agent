"""MCP connection manager (spec §5).

Singleton service owning one client session per active mcp_server record.
Each connection lives in its own asyncio task that holds the client context
open; tools/list results are upserted into the tools registry with source
inherited from the server; listChanged notifications trigger reconciliation;
a ping loop (interval from settings, live) flips failing servers to 'error'.
DB is the source of truth — startup loads and connects every non-deleted
server, so dynamic records survive restarts.

M53 (arch-H10): a server that fails to connect, or fails a health ping, is
RECONNECTED automatically with exponential backoff (5 s doubling to 5 min)
behind its own gate (`mcp_auto_reconnect_enabled`); after
`mcp_reconnect_max_attempts` consecutive failures the circuit opens — the
row says so and the operator's reconnect button resets it. Re-ingest keeps
operator intent: a tool the operator disabled or deleted stays that way
when the server still offers it; only a tool the SERVER dropped is marked
inactive, and only that tool is reactivated when it comes back.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import mcp.types as mcp_types
import structlog
from langchain_core.tools import BaseTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import obs
from app.db import get_session_factory
from app.models import McpServer, Tool

logger = structlog.get_logger("mcp.manager")

CONNECT_TIMEOUT_S = 25.0
# M54: per-server ingest lock (transaction-scoped) — its own classid
INGEST_LOCK_CLASSID = 427020
PING_TIMEOUT_S = 5.0

# The MCP SDK spawns stdio servers with a minimal default environment, which
# strips deployment-level network config — behind a proxy, uvx/npx launchers
# can't reach their registries. Pass these through; server.env still wins.
_STDIO_ENV_PASSTHROUGH = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "NODE_OPTIONS",
)
_STDIO_ENV_PREFIXES = ("UV_", "npm_config_")


def _stdio_env(server_env: dict[str, Any] | None) -> dict[str, str]:
    import os

    from mcp.client.stdio import get_default_environment

    from app.mcp.secrets import resolve_secret_map

    env = get_default_environment()
    for key, value in os.environ.items():
        if key in _STDIO_ENV_PASSTHROUGH or key.startswith(_STDIO_ENV_PREFIXES):
            env[key] = value
    env.update(resolve_secret_map(server_env))  # M52: env:VAR indirection
    return env


class _Connection:
    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.task: asyncio.Task[None] | None = None
        self.ready = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.error: BaseException | None = None


@dataclass
class _Breaker:
    """Per-server reconnect budget (M53)."""

    attempts: int = 0
    circuit_open: bool = False
    task: asyncio.Task[None] | None = None
    next_attempt_at: float | None = None


class McpManager:
    RECONNECT_BASE_S = 5.0
    RECONNECT_CAP_S = 300.0

    def __init__(self) -> None:
        self._conns: dict[UUID, _Connection] = {}
        self._breakers: dict[UUID, _Breaker] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._seen: set[UUID] = set()  # M54: servers this replica has attempted

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self, connect_timeout: float = CONNECT_TIMEOUT_S) -> None:
        """Connect every non-deleted server (spec §5 startup) + health loop."""
        async with get_session_factory()() as db:
            server_ids = list(
                (
                    await db.execute(select(McpServer.id).where(McpServer.deleted_at.is_(None)))
                ).scalars()
            )
        self._seen.update(server_ids)
        await asyncio.gather(
            *(self.connect_server(sid, timeout_s=connect_timeout) for sid in server_ids),
            return_exceptions=True,
        )
        if self._health_task is None:
            self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_task
            self._health_task = None
        for breaker in self._breakers.values():
            self._cancel_reconnect(breaker)
        for server_id in list(self._conns):
            await self._teardown(server_id)
        self._publish_states()

    # ── connection ───────────────────────────────────────────────

    async def connect_server(self, server_id: UUID, timeout_s: float = CONNECT_TIMEOUT_S) -> None:
        """(Re)connect, ingest tools, and record status on the server row.
        An explicit connect — startup, the operator's button — resets the
        reconnect budget and closes an open circuit; a failure schedules
        the automatic retry (if the gate allows)."""
        breaker = self._breaker(server_id)
        self._cancel_reconnect(breaker)
        breaker.attempts = 0
        breaker.circuit_open = False
        self._seen.add(server_id)
        if not await self._connect_once(server_id, timeout_s):
            await self._schedule_reconnect(server_id)
        self._publish_states()

    async def _connect_once(self, server_id: UUID, timeout_s: float = CONNECT_TIMEOUT_S) -> bool:
        await self._teardown(server_id)
        async with get_session_factory()() as db:
            server = await db.get(McpServer, server_id)
            if server is None or server.deleted_at is not None:
                return True  # nothing to connect — not a failure to retry
        conn = _Connection()
        self._conns[server_id] = conn
        conn.task = asyncio.create_task(self._run_connection(server, conn))
        try:
            await asyncio.wait_for(conn.ready.wait(), timeout=timeout_s)
            if conn.error is not None:
                raise conn.error
            await self._ingest(server_id)
        except BaseException as exc:  # noqa: BLE001 - connection failure path
            from app.mcp.secrets import secret_strings

            await self._teardown(server_id)
            described = _describe(
                exc, secrets=secret_strings(server.env) + secret_strings(server.headers)
            )
            await self._record_status(server_id, "error", error=described)
            logger.warning("mcp_connect_failed", server_id=str(server_id), error=described)
            return False
        await self._record_status(server_id, "active", connected=True)
        logger.info("mcp_connected", server_id=str(server_id), server_name=server.name)
        return True

    async def _run_connection(self, server: McpServer, conn: _Connection) -> None:
        try:
            if server.transport == "stdio":
                params = StdioServerParameters(
                    command=server.command or "",
                    args=[str(a) for a in (server.args or [])],
                    env=_stdio_env(server.env),
                )
                client_ctx: Any = stdio_client(params)
            else:
                from app import egress
                from app.mcp.secrets import resolve_secret_map

                # M52: the server URL is judged by the egress policy before
                # a connection is attempted, the SDK's own client carries
                # the policy hook, and header secrets resolve env: here
                egress.check_url_static(server.url or "")
                headers = resolve_secret_map(server.headers)
                client_ctx = streamablehttp_client(
                    server.url or "",
                    headers=headers or None,
                    httpx_client_factory=egress.mcp_client_factory,
                )
            async with client_ctx as streams:
                read, write = streams[0], streams[1]

                async def on_message(message: Any) -> None:
                    self._handle_notification(server.id, message)

                async with ClientSession(read, write, message_handler=on_message) as session:
                    await session.initialize()
                    conn.session = session
                    conn.ready.set()
                    await conn.stop_event.wait()
        except BaseException as exc:  # noqa: BLE001 - report to connect_server
            conn.error = exc
        finally:
            conn.session = None
            conn.ready.set()

    async def _teardown(self, server_id: UUID) -> None:
        conn = self._conns.pop(server_id, None)
        if conn is None:
            return
        conn.stop_event.set()
        if conn.task is not None:
            conn.task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(conn.task, timeout=5)

    async def disconnect_server(self, server_id: UUID) -> None:
        """An operator's disconnect or delete: no automatic retry follows."""
        breaker = self._breakers.pop(server_id, None)
        if breaker is not None:
            self._cancel_reconnect(breaker)
        await self._teardown(server_id)
        self._publish_states()

    # ── reconnection with backoff + circuit breaker (M53) ────────

    def _breaker(self, server_id: UUID) -> _Breaker:
        return self._breakers.setdefault(server_id, _Breaker())

    @staticmethod
    def _cancel_reconnect(breaker: _Breaker) -> None:
        task, breaker.task = breaker.task, None
        breaker.next_attempt_at = None
        if task is not None and not task.done():
            task.cancel()

    def reconnect_state(self, server_id: UUID) -> dict[str, Any]:
        breaker = self._breakers.get(server_id) or _Breaker()
        return {
            "attempts": breaker.attempts,
            "circuit_open": breaker.circuit_open,
            "scheduled": breaker.task is not None and not breaker.task.done(),
            "next_attempt_at": breaker.next_attempt_at,
        }

    async def _reconnect_policy(self) -> tuple[bool, int]:
        from app.registry_cache import get_cache

        try:
            enabled = bool(await get_cache().setting("mcp_auto_reconnect_enabled"))
            max_attempts = max(int(await get_cache().setting("mcp_reconnect_max_attempts") or 1), 1)
        except Exception:  # noqa: BLE001 — a settings hiccup must not stop a reconnect
            enabled, max_attempts = True, 8
        return enabled, max_attempts

    async def _schedule_reconnect(self, server_id: UUID) -> None:
        breaker = self._breaker(server_id)
        if breaker.circuit_open or (breaker.task is not None and not breaker.task.done()):
            return
        enabled, _ = await self._reconnect_policy()
        if not enabled:
            return
        breaker.task = asyncio.create_task(self._reconnect_loop(server_id))
        self._publish_states()

    async def _reconnect_loop(self, server_id: UUID) -> None:
        breaker = self._breaker(server_id)
        loop = asyncio.get_running_loop()
        try:
            while True:
                enabled, max_attempts = await self._reconnect_policy()
                if not enabled:
                    return
                breaker.attempts += 1
                delay = min(
                    self.RECONNECT_BASE_S * 2 ** (breaker.attempts - 1), self.RECONNECT_CAP_S
                )
                breaker.next_attempt_at = loop.time() + delay
                logger.info(
                    "mcp_reconnect_scheduled",
                    server_id=str(server_id),
                    attempt=breaker.attempts,
                    delay_s=round(delay, 3),
                )
                await asyncio.sleep(delay)
                breaker.next_attempt_at = None
                if await self._connect_once(server_id):
                    breaker.attempts = 0
                    obs.MCP_RECONNECTS.labels(outcome="ok").inc()
                    logger.info("mcp_reconnected", server_id=str(server_id))
                    return
                obs.MCP_RECONNECTS.labels(outcome="failed").inc()
                if breaker.attempts >= max_attempts:
                    breaker.circuit_open = True
                    obs.MCP_RECONNECTS.labels(outcome="circuit_open").inc()
                    await self._record_status(
                        server_id,
                        "error",
                        error=(
                            f"circuit open after {breaker.attempts} failed reconnect attempts "
                            f"(mcp_reconnect_max_attempts) — reconnect manually"
                        ),
                    )
                    logger.warning(
                        "mcp_circuit_open", server_id=str(server_id), attempts=breaker.attempts
                    )
                    return
        finally:
            breaker.task = None
            breaker.next_attempt_at = None
            self._publish_states()

    def _publish_states(self) -> None:
        connected = sum(1 for c in self._conns.values() if c.session is not None)
        reconnecting = sum(
            1 for b in self._breakers.values() if b.task is not None and not b.task.done()
        )
        circuit_open = sum(1 for b in self._breakers.values() if b.circuit_open)
        obs.MCP_SERVERS.labels(state="connected").set(connected)
        obs.MCP_SERVERS.labels(state="reconnecting").set(reconnecting)
        obs.MCP_SERVERS.labels(state="circuit_open").set(circuit_open)

    # ── ingest / reconcile (spec §5 register + listChanged) ─────

    async def refresh_tools(self, server_id: UUID) -> None:
        await self._ingest(server_id)

    async def _ingest(self, server_id: UUID) -> None:
        conn = self._conns.get(server_id)
        if conn is None or conn.session is None:
            raise RuntimeError(f"server {server_id} is not connected")
        result = await conn.session.list_tools()
        async with get_session_factory()() as db:
            # M54 (scale-H6): N replicas ingest the same server at once — a
            # per-server transaction advisory lock serializes the reconcile,
            # and the insert upserts on (server, tool name) so a racer that
            # got in first is folded into, never collided with
            await db.execute(
                sql_text("SELECT pg_advisory_xact_lock(:c, :o)"),
                {"c": INGEST_LOCK_CLASSID, "o": server_id.int % (2**31)},
            )
            server = await db.get(McpServer, server_id)
            if server is None:
                return
            existing = {
                t.tool_name: t
                for t in (
                    await db.execute(select(Tool).where(Tool.mcp_server_id == server_id))
                ).scalars()
            }
            taken_keys = set((await db.execute(select(Tool.tool_key))).scalars())
            seen: set[str] = set()
            for spec in result.tools:
                seen.add(spec.name)
                row = existing.get(spec.name)
                if row is None:
                    key = f"{server.name}.{spec.name}"
                    if key in taken_keys:  # collision-safe (spec §3.2)
                        key = f"{key}-{uuid4().hex[:6]}"
                    taken_keys.add(key)
                    stmt = pg_insert(Tool).values(
                        id=uuid4(),
                        name=spec.name,
                        description=spec.description or "",
                        kind="mcp",
                        source=server.source,  # inherited (spec §5)
                        status="active",
                        mcp_server_id=server_id,
                        tool_name=spec.name,
                        tool_key=key,
                        direct_exposure=False,
                        input_schema=spec.inputSchema,
                        ingest_state="present",
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["mcp_server_id", "tool_name"],
                        index_where=sql_text("mcp_server_id IS NOT NULL"),
                        set_={
                            "description": stmt.excluded.description,
                            "input_schema": stmt.excluded.input_schema,
                            "ingest_state": "present",
                        },
                    )
                    await db.execute(stmt)
                else:
                    row.description = spec.description or ""
                    row.input_schema = spec.inputSchema
                    # M53: only the SERVER's absence is undone by its return;
                    # an operator's inactive (or deleted) row stays as set
                    if row.ingest_state == "missing" and row.deleted_at is None:
                        row.status = "active"
                    row.ingest_state = "present"
            for name, row in existing.items():
                if name not in seen:
                    if row.status == "active":
                        row.status = "inactive"  # removed tools marked inactive
                        row.ingest_state = "missing"
                    elif row.ingest_state == "present":
                        # the operator disabled it AND the server dropped it:
                        # keep the operator's word — a return must not reactivate
                        row.ingest_state = None
            await db.commit()
        from app.registry_cache import get_cache

        await get_cache().invalidate("tools")
        logger.info(
            "mcp_tools_ingested",
            server_id=str(server_id),
            tool_count=len(result.tools),
        )

    def _handle_notification(self, server_id: UUID, message: Any) -> None:
        root = getattr(message, "root", None)
        if isinstance(root, mcp_types.ToolListChangedNotification):
            logger.info("mcp_list_changed", server_id=str(server_id))
            task = asyncio.create_task(self._safe_refresh(server_id))
            task.add_done_callback(lambda t: t.exception())

    async def _safe_refresh(self, server_id: UUID) -> None:
        with contextlib.suppress(Exception):
            await self._ingest(server_id)

    # ── health (spec §5) ─────────────────────────────────────────

    async def ping_all(self) -> None:
        for server_id, conn in list(self._conns.items()):
            session = conn.session
            ok = False
            if session is not None:
                try:
                    await asyncio.wait_for(session.send_ping(), timeout=PING_TIMEOUT_S)
                    ok = True
                except BaseException:  # noqa: BLE001 — a ping failure of any kind marks the server unhealthy
                    ok = False
            if not ok:
                await self._teardown(server_id)
                await self._record_status(server_id, "error", error="health ping failed")
                logger.warning("mcp_ping_failed", server_id=str(server_id))
                await self._schedule_reconnect(server_id)  # M53
        self._publish_states()

    async def reconcile(self) -> dict[str, int]:
        """M54 (spec §18.9): each replica reconciles ITS subprocess set
        against the registry — a server registered through another replica
        is connected here, one deleted elsewhere is torn down here. Servers
        this replica already tried (in error, mid-reconnect, or with the
        circuit open) are left to the reconnect machinery."""
        async with get_session_factory()() as db:
            wanted = set(
                (
                    await db.execute(select(McpServer.id).where(McpServer.deleted_at.is_(None)))
                ).scalars()
            )
        connected = added = removed = 0
        for server_id in list(self._conns):
            if server_id not in wanted:
                await self.disconnect_server(server_id)
                self._seen.discard(server_id)
                removed += 1
        for server_id in wanted:
            if server_id in self._conns or server_id in self._seen:
                continue
            self._seen.add(server_id)
            await self.connect_server(server_id)
            added += 1
        connected = sum(1 for c in self._conns.values() if c.session is not None)
        if added or removed:
            logger.info("mcp_reconciled", added=added, removed=removed, connected=connected)
        return {"added": added, "removed": removed, "connected": connected}

    async def _health_loop(self) -> None:
        from app.settings_store import get_setting

        while True:
            try:
                async with get_session_factory()() as db:
                    interval = int(await get_setting(db, "mcp_health_interval_s"))
                await asyncio.sleep(max(interval, 1))
                await self.reconcile()  # M54: the registry is the fleet's truth
                await self.ping_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the health loop must survive anything
                obs.LOOP_ERRORS.labels(loop="mcp_health").inc()
                logger.warning("mcp_health_tick_failed", error=str(exc)[:200])
                await asyncio.sleep(5)

    # ── invocation (spec §5): bound tools as LangChain tools ────

    async def get_langchain_tools(self, server_id: UUID, tool_names: list[str]) -> list[BaseTool]:
        conn = self._conns.get(server_id)
        if conn is None or conn.session is None:
            raise RuntimeError(f"MCP server {server_id} is not connected")
        from langchain_mcp_adapters.tools import load_mcp_tools

        tools = await load_mcp_tools(conn.session)
        wanted = set(tool_names)
        return [t for t in tools if t.name in wanted]

    def is_connected(self, server_id: UUID) -> bool:
        conn = self._conns.get(server_id)
        return conn is not None and conn.session is not None

    # ── helpers ──────────────────────────────────────────────────

    async def _record_status(
        self, server_id: UUID, status: str, error: str | None = None, connected: bool = False
    ) -> None:
        async with get_session_factory()() as db:
            server = await db.get(McpServer, server_id)
            if server is None:
                return
            server.status = status
            server.last_error = error
            if connected:
                server.last_connected_at = datetime.now(UTC)
            await db.commit()


def _describe(exc: BaseException, *, secrets: list[str] | None = None) -> str:
    """Error text for the row — through the one sanitizer (M52), with the
    server's own env/header values as extra secrets."""
    from app.sanitize import sanitize_error

    if isinstance(exc, TimeoutError):
        return "connection timed out"
    if isinstance(exc, BaseExceptionGroup):
        parts = [_describe(e, secrets=secrets) for e in exc.exceptions]
        return "; ".join(dict.fromkeys(parts))
    raw = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    return sanitize_error(raw, extra_secrets=secrets or ()) or raw


_manager: McpManager | None = None


def get_manager() -> McpManager | None:
    return _manager


def set_manager(manager: McpManager | None) -> None:
    global _manager
    _manager = manager
