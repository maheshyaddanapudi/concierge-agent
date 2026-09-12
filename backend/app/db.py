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


# M54 (spec §18.9, scale-B2): the connection budget, declared and checked.
# Per replica: the pooled ceiling, the LangGraph checkpointer pool, and the
# session-level connections that cannot go through a transaction-mode pooler
# (two supervised LISTENs, the control listener, the ambient leader lease).
CHECKPOINTER_POOL = 10
SESSION_CONNECTIONS = 4
# headroom for migrations, psql, the load harness and Postgres' own
# superuser reserve — outside any replica's share
RESERVED_CONNECTIONS = 10


def engine_connect_args() -> dict[str, Any]:
    """asyncpg's statement cache and SQLAlchemy's prepared-statement cache,
    both sized by DB_STATEMENT_CACHE_SIZE (default 0): a transaction-mode
    pooler hands the next statement to a different server connection, where
    a cached prepared statement does not exist — the classic
    DuplicatePreparedStatementError. 0 costs a re-prepare per statement and
    survives any pooler; the session connections are direct by design."""
    size = int(get_config().db_statement_cache_size)
    return {"statement_cache_size": size, "prepared_statement_cache_size": size}


def connection_budget() -> dict[str, Any]:
    """The arithmetic, published (GET /replicas) and checked at boot."""
    cfg = get_config()
    per_replica = (
        int(cfg.db_pool_size) + int(cfg.db_max_overflow) + CHECKPOINTER_POOL + SESSION_CONNECTIONS
    )
    replicas = max(int(cfg.db_replicas), 1)
    needed = replicas * per_replica + RESERVED_CONNECTIONS
    declared = int(cfg.db_max_connections)
    return {
        "per_replica": per_replica,
        "pool": int(cfg.db_pool_size),
        "overflow": int(cfg.db_max_overflow),
        "checkpointer": CHECKPOINTER_POOL,
        "sessions": SESSION_CONNECTIONS,
        "replicas": replicas,
        "reserved": RESERVED_CONNECTIONS,
        "needed": needed,
        "declared_max": declared,
        "fits": needed <= declared,
        "max_replicas_at_declared": max((declared - RESERVED_CONNECTIONS) // per_replica, 0),
    }


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
            connect_args=engine_connect_args(),  # M54: pooler-safe by default
        )
        from app.obs import bind_pool_gauges

        bind_pool_gauges(_engine)  # M53: pool saturation on /metrics
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
