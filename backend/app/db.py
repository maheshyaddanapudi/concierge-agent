"""Async SQLAlchemy engine and session factory."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_config

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# M51: sessions open per asyncio task. The fake provider refuses a call
# made while one is open (strict mode in tests), which is how the rule
# "no session spans a provider call" (spec §16.2, arch-H8/H15) is enforced
# rather than documented. Keyed by task id, never a ContextVar: a task
# spawned inside a request handler must not inherit the handler's count.
_OPEN: dict[int, int] = {}


def _task_key() -> int:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return id(task) if task is not None else 0


def open_sessions() -> int:
    """How many tracked sessions the CURRENT task holds open."""
    return _OPEN.get(_task_key(), 0)


class TrackedSession(AsyncSession):
    """AsyncSession that counts itself while entered as a context manager."""

    async def __aenter__(self) -> "TrackedSession":
        key = _task_key()
        _OPEN[key] = _OPEN.get(key, 0) + 1
        self._tracked_key = key
        return self

    async def __aexit__(self, *exc: Any) -> None:
        key = getattr(self, "_tracked_key", _task_key())
        left = _OPEN.get(key, 1) - 1
        if left <= 0:
            _OPEN.pop(key, None)
        else:
            _OPEN[key] = left
        await super().__aexit__(*exc)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = get_config()
        _engine = create_async_engine(
            cfg.database_url,
            pool_pre_ping=True,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_timeout=cfg.db_pool_timeout,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=TrackedSession
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with get_session_factory()() as session:
        yield session


_checkpointer: Any = None
_checkpointer_pool: Any = None


async def get_checkpointer() -> Any:
    """Shared LangGraph Postgres checkpointer (spec §6) — required for HITL
    pause/resume; threads are keyed by run_id."""
    global _checkpointer, _checkpointer_pool
    if _checkpointer is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        url = get_config().database_url.replace("+asyncpg", "")
        _checkpointer_pool = AsyncConnectionPool(
            url,
            open=False,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await _checkpointer_pool.open()
        _checkpointer = AsyncPostgresSaver(_checkpointer_pool)
        await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _checkpointer_pool
    if _checkpointer_pool is not None:
        await _checkpointer_pool.close()
    _checkpointer = None
    _checkpointer_pool = None


def reset_db_state() -> None:
    """Testing hook: forget cached engine/factory so a new DATABASE_URL applies."""
    global _engine, _session_factory, _checkpointer, _checkpointer_pool
    _engine = None
    _session_factory = None
    _checkpointer = None
    _checkpointer_pool = None
