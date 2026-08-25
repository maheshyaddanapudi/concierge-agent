"""FastAPI application factory and startup lifecycle."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.db import get_session_factory
from app.llm.registry import register_builtin_providers
from app.native.provider import scan_native

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(_run_migrations)
    async with get_session_factory()() as session:
        from app.seed.loader import seed_all

        await seed_all(session)
        # spec §5b/§10: explicitly stored log_level / otlp_endpoint override
        # the env bootstrap; absent rows keep the env-configured defaults
        from app.models import AppSetting
        from app.obs import apply_otlp_endpoint, configure_logging

        row = await session.get(AppSetting, "log_level")
        if row is not None:
            configure_logging(str(row.value.get("value")))
        row = await session.get(AppSetting, "otlp_endpoint")
        if row is not None:
            apply_otlp_endpoint(str(row.value.get("value") or ""))
    from app.db import close_checkpointer, get_checkpointer
    from app.mcp.manager import McpManager, set_manager

    await get_checkpointer()  # create checkpoint tables up front
    from app.registry_cache import get_cache
    from app.retrieval import backfill_embeddings

    await get_cache().startup()  # registry cache (spec §7.3): mode + warm load
    manager = McpManager()
    set_manager(manager)
    # connect persisted servers without blocking app readiness
    startup_task = asyncio.create_task(manager.start())
    # retrieval (spec §7.4): embed stale records without blocking readiness
    backfill_task = asyncio.create_task(backfill_embeddings())
    # memory consolidation loop (spec §16.2) — cheap ticks when memory is off
    from app.memory.lifecycle import run_periodic_loop

    memory_stop = asyncio.Event()
    memory_loop_task = asyncio.create_task(run_periodic_loop(memory_stop))
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
    yield
    ambient_stop.set()
    ambient_loop_task.cancel()
    memory_stop.set()
    memory_loop_task.cancel()
    from app.memory.scheduler import shutdown as memory_shutdown

    memory_shutdown()
    backfill_task.cancel()
    await get_cache().stop_listener()
    startup_task.cancel()
    await manager.stop()
    set_manager(None)
    await close_checkpointer()


def create_app(with_lifespan: bool = True) -> FastAPI:
    from app.config import get_config
    from app.obs import bootstrap_otel_from_env, configure_logging

    configure_logging(get_config().log_level)
    bootstrap_otel_from_env()
    register_builtin_providers()
    scan_native()
    app = FastAPI(title="Concierge Agent", lifespan=lifespan if with_lifespan else None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
