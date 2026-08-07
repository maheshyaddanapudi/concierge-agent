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
    yield
    backfill_task.cancel()
    await get_cache().stop_listener()
    startup_task.cancel()
    await manager.stop()
    set_manager(None)
    await close_checkpointer()


def create_app(with_lifespan: bool = True) -> FastAPI:
    from app.config import get_config
    from app.obs import configure_logging

    configure_logging(get_config().log_level)
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
