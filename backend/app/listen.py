"""Supervised LISTEN connections (M53, arch-H10 / M7).

Both listeners the process holds — the registry-cache invalidation channel
and the ambient wake channel — used to open one asyncpg connection at boot
and never look at it again: a Postgres restart, a failover, or an idle-
timeout on a NAT left the process deaf for the rest of its life, with no
signal on `/metrics`. This supervisor owns the connection instead: it
reconnects with backoff when the connection is lost (asyncpg's termination
listener plus a heartbeat probe, so a half-open socket is caught too), tells
its owner when it is back — the owner reloads whatever it may have missed —
and exports `concierge_listener_connected{channel}` so a deaf replica is a
visible one.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

import structlog

from app import obs
from app.config import get_config

logger = structlog.get_logger("listen")


class SupervisedListener:
    def __init__(
        self,
        channel: str,
        on_notify: Callable[[str], Any],
        *,
        on_reconnect: Callable[[], Any] | None = None,
        base_backoff_s: float = 1.0,
        max_backoff_s: float = 30.0,
        heartbeat_s: float = 10.0,
    ) -> None:
        self.channel = channel
        self._on_notify = on_notify
        self._on_reconnect = on_reconnect
        self._base = max(base_backoff_s, 0.01)
        self._max = max(max_backoff_s, self._base)
        self._heartbeat_s = max(heartbeat_s, 0.05)
        self._conn: Any = None
        self._task: asyncio.Task[None] | None = None
        self._lost: asyncio.Event | None = None
        self._first_attempt: asyncio.Event | None = None
        self._stopping = False
        self._connected = False
        self._ever_connected = False
        self.reconnects = 0

    # ── state ────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    def server_pid(self) -> int | None:
        conn = self._conn
        if conn is None or conn.is_closed():
            return None
        return int(conn.get_server_pid())

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self, first_attempt_timeout_s: float = 5.0) -> bool:
        """Start supervising. Waits for the first connect attempt (bounded)
        so a caller can log the outcome; the supervisor keeps retrying in
        the background either way. Returns whether the first attempt held."""
        if self._task is not None and not self._task.done():
            return self._connected
        self._stopping = False
        self._first_attempt = asyncio.Event()
        self._task = asyncio.create_task(self._supervise(), name=f"listen:{self.channel}")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._first_attempt.wait(), timeout=first_attempt_timeout_s)
        return self._connected

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(task, timeout=5)
        await self._close()
        self._set_connected(False)

    # ── supervisor ───────────────────────────────────────────────

    async def _supervise(self) -> None:
        delay = self._base
        while not self._stopping:
            try:
                await self._connect()
            except Exception as exc:  # noqa: BLE001 — every failure here is retried with backoff
                self._signal_first_attempt()
                logger.warning(
                    "listener_connect_failed",
                    channel=self.channel,
                    error=str(exc)[:200],
                    retry_in_s=delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max)
                continue
            self._signal_first_attempt()
            delay = self._base
            if self._ever_connected:
                self.reconnects += 1
                obs.LISTENER_RECONNECTS.labels(channel=self.channel).inc()
                logger.info(
                    "listener_reconnected", channel=self.channel, reconnects=self.reconnects
                )
                if self._on_reconnect is not None:
                    try:
                        self._on_reconnect()
                    except Exception as exc:  # noqa: BLE001 — the owner's reload must not kill the supervisor
                        logger.warning(
                            "listener_reconnect_hook_failed", channel=self.channel, error=str(exc)
                        )
            self._ever_connected = True
            await self._watch()
            self._set_connected(False)
            await self._close()
            if self._stopping:
                break
            logger.warning("listener_lost", channel=self.channel, retry_in_s=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max)

    def _signal_first_attempt(self) -> None:
        if self._first_attempt is not None:
            self._first_attempt.set()

    async def _connect(self) -> None:
        import asyncpg  # type: ignore[import-untyped]

        dsn = get_config().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        # the session is named in pg_stat_activity.application_name so an
        # operator can tell the listeners from the pool (and a drill can
        # terminate exactly them): `concierge-listen:<channel>`
        conn = await asyncpg.connect(
            dsn, server_settings={"application_name": f"concierge-listen:{self.channel}"}
        )
        lost = asyncio.Event()
        try:
            await conn.add_listener(self.channel, self._on_message)
            conn.add_termination_listener(lambda _c: lost.set())
        except Exception:
            with contextlib.suppress(Exception):
                await conn.close()
            raise
        self._conn = conn
        self._lost = lost
        self._set_connected(True)
        logger.info("listener_started", channel=self.channel, pid=self.server_pid())

    async def _watch(self) -> None:
        """Return when the current connection is gone: asyncpg tells us on a
        clean close or a server-side termination; the heartbeat catches a
        socket that died without a word."""
        lost = self._lost
        conn = self._conn
        if lost is None or conn is None:
            return
        while not self._stopping:
            try:
                await asyncio.wait_for(lost.wait(), timeout=self._heartbeat_s)
                return
            except TimeoutError:
                if conn.is_closed():
                    return
                try:
                    await asyncio.wait_for(conn.execute("SELECT 1"), timeout=self._heartbeat_s)
                except Exception:  # noqa: BLE001 — any probe failure means the connection is gone
                    return

    async def _close(self) -> None:
        conn, self._conn = self._conn, None
        self._lost = None
        if conn is not None and not conn.is_closed():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(conn.close(), timeout=2)

    def _set_connected(self, value: bool) -> None:
        self._connected = value
        obs.LISTENER_CONNECTED.labels(channel=self.channel).set(1.0 if value else 0.0)

    def _on_message(self, _conn: Any, _pid: int, _channel: str, payload: str) -> None:
        try:
            self._on_notify(str(payload))
        except Exception as exc:  # noqa: BLE001 — a bad payload must not tear the listener down
            logger.warning("listener_callback_failed", channel=self.channel, error=str(exc))
