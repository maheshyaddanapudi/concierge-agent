"""FastAPI application factory and startup lifecycle."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.db import get_session_factory
from app.llm.registry import register_builtin_providers
from app.native.provider import scan_native

BACKEND_DIR = Path(__file__).resolve().parents[1]
READY_DB_TIMEOUT_S = 2.0


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


async def _settle(task: asyncio.Task[Any], timeout_s: float = 10.0) -> None:
    """M53: a cancelled loop is AWAITED so its finalizers run — the ambient
    loop releases the leader lease on the way out, which is what lets the
    next replica lead within one tick instead of waiting for a dead session
    to lapse."""
    with contextlib.suppress(BaseException):
        await asyncio.wait_for(task, timeout=timeout_s)


async def _db_probe() -> None:
    """One fresh, short-lived connection — deliberately NOT the pool, so an
    exhausted or wedged pool cannot make the probe hang (the pool has its
    own gauge, `concierge_db_pool_saturation`). Every stage carries its own
    timeout: a database that accepts the socket but never answers (paused,
    partitioned) still fails the probe inside READY_DB_TIMEOUT_S."""
    import asyncpg  # type: ignore[import-untyped]

    from app.config import get_config

    dsn = get_config().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn, timeout=READY_DB_TIMEOUT_S)
    try:
        await conn.fetchval("SELECT 1", timeout=READY_DB_TIMEOUT_S)
    finally:
        with contextlib.suppress(Exception):
            await conn.close(timeout=READY_DB_TIMEOUT_S)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app import control
    from app.db import connection_budget
    from app.replica import boot_lock, replica_id, run_replica_heartbeat_loop

    # M54 (spec §18.9): N replicas booting together migrate and seed ONCE —
    # the boot lock serializes them on a dedicated session connection
    async with boot_lock():
        await asyncio.to_thread(_run_migrations)
        async with get_session_factory()() as session:
            from app.seed.loader import seed_all

            await seed_all(session)
            # spec §5b/§10: explicitly stored log_level / otlp_endpoint
            # override the env bootstrap; absent rows keep the env defaults
            from app.models import AppSetting
            from app.obs import apply_otlp_endpoint, configure_logging

            row = await session.get(AppSetting, "log_level")
            if row is not None:
                configure_logging(str(row.value.get("value")))
            row = await session.get(AppSetting, "otlp_endpoint")
            if row is not None:
                apply_otlp_endpoint(str(row.value.get("value") or ""))
    budget = connection_budget()
    _log = structlog.get_logger("boot")
    (_log.warning if not budget["fits"] else _log.info)(
        "db_connection_budget", replica=replica_id(), **budget
    )
    from app.db import close_checkpointer, get_checkpointer
    from app.mcp.manager import McpManager, set_manager

    await get_checkpointer()  # create checkpoint tables up front
    # M51: runs left running/queued by the previous process cannot resume
    from app.orchestrator.runner import drain_running_tasks, reap_orphaned_runs

    await reap_orphaned_runs()
    from app.registry_cache import get_cache
    from app.retrieval import backfill_embeddings

    await get_cache().startup()  # registry cache (spec §7.3): mode + warm load
    manager = McpManager()
    set_manager(manager)
    # connect persisted servers without blocking app readiness
    startup_task = asyncio.create_task(manager.start())
    # A2A manager (spec §19.2) — card refresh loop no-ops while a2a is dark
    from app.a2a.manager import A2AManager
    from app.a2a.manager import set_manager as set_a2a_manager

    a2a_manager = A2AManager()
    set_a2a_manager(a2a_manager)
    a2a_startup_task = asyncio.create_task(a2a_manager.start())
    # retrieval (spec §7.4): embed stale records without blocking readiness
    backfill_task = asyncio.create_task(backfill_embeddings())
    # memory consolidation loop (spec §16.2) — cheap ticks when memory is off;
    # M53: the same loop ticks retention and refreshes provider price feeds
    from app.memory.lifecycle import run_periodic_loop

    memory_stop = asyncio.Event()
    memory_loop_task = asyncio.create_task(run_periodic_loop(memory_stop))
    # §18.8: with auth on, ensure the bootstrap admin exists (one-time
    # password prints to this log)
    from app.auth import auth_enabled, bootstrap_admin

    if auth_enabled():
        await bootstrap_admin()
    # native poll sources + state probes (spec §18.3) — registered every
    # boot so the tick and the watch compiler see the live registries
    from app.ambient.sources import register_native_sources

    register_native_sources()
    # delivery channel adapters (spec §18.4) — in_app is the outbox itself
    from app.ambient.channels import register_native_channels

    register_native_channels()
    # ambient drain loop (spec §17.2) — cheap ticks while ambient is dark
    from app.ambient.drain import run_ambient_loop

    ambient_stop = asyncio.Event()
    ambient_loop_task = asyncio.create_task(run_ambient_loop(ambient_stop))
    from app.orchestrator import admission

    admission.set_accepting(True)
    # M53: SIGUSR1 is the pre-stop hook — readiness goes 503 while the port
    # is still open, so a balancer stops routing here BEFORE SIGTERM
    admission.install_drain_signal()
    # M54: this replica's heartbeat row and the control channel it listens on
    replica_stop = asyncio.Event()
    replica_task = asyncio.create_task(run_replica_heartbeat_loop(replica_stop))
    await control.start_listener()
    yield
    # M51 shutdown: readiness off → stop accepting → drain in-flight runs
    # within the grace period → cancel the rest (each finalizes terminal)
    from app.config import get_config as _cfg

    await drain_running_tasks(grace_s=float(_cfg().shutdown_grace_s))
    replica_stop.set()
    await _settle(replica_task)  # retires this replica's row (M54)
    await control.stop_listener()
    ambient_stop.set()
    ambient_loop_task.cancel()
    await _settle(ambient_loop_task)  # releases the leader lease (M53)
    memory_stop.set()
    memory_loop_task.cancel()
    await _settle(memory_loop_task)
    from app.memory.scheduler import shutdown as memory_shutdown

    memory_shutdown()
    backfill_task.cancel()
    await get_cache().stop_listener()
    startup_task.cancel()
    await manager.stop()
    set_manager(None)
    a2a_startup_task.cancel()
    await a2a_manager.stop()
    set_a2a_manager(None)
    await close_checkpointer()


def create_app(with_lifespan: bool = True) -> FastAPI:
    from app.config import get_config
    from app.obs import bootstrap_otel_from_env, configure_logging

    configure_logging(get_config().log_level)
    bootstrap_otel_from_env()
    register_builtin_providers()
    scan_native()
    app = FastAPI(title="Concierge Agent", lifespan=lifespan if with_lifespan else None)
    # §18.8: with auth on, CORS pins to the frontend origin; dark keeps '*'
    pinned = get_config().frontend_origin
    origins: list[str] = [pinned] if get_config().auth_enabled and pinned else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.auth import AuthMiddleware

    app.add_middleware(AuthMiddleware)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness: the process is up and its loop answers. Never probes a
        dependency — a replica whose database is away must not be killed
        for it, only taken out of rotation (that is /ready's job)."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> Response:
        """Readiness (M51/M53): 503 while draining so a balancer stops
        routing here, and 503 `degraded` when the database does not answer
        within READY_DB_TIMEOUT_S — a replica that cannot reach Postgres
        cannot serve a run. /health stays liveness."""
        import json as _json

        from app.orchestrator import admission
        from app.sanitize import sanitize_error

        snap = admission.snapshot()
        db = "ok"
        try:
            # the probe's own stage timeouts add up to at most 3× the budget;
            # this outer bound is the backstop
            await asyncio.wait_for(_db_probe(), timeout=READY_DB_TIMEOUT_S * 3)
        except Exception as exc:  # noqa: BLE001 — any failure means "not ready", named
            db = f"error: {sanitize_error(str(exc)) or type(exc).__name__}"[:200]
        if not snap["accepting"]:
            status = "draining"
        elif db != "ok":
            status = "degraded"
        else:
            status = "ready"
        return Response(
            content=_json.dumps({"status": status, "db": db, **snap}),
            media_type="application/json",
            status_code=200 if status == "ready" else 503,
        )

    @app.get("/metrics")
    async def metrics() -> Response:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
