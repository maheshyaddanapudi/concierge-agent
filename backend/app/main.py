"""FastAPI application factory and startup lifecycle."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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
    yield


def create_app(with_lifespan: bool = True) -> FastAPI:
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

    return app


app = create_app()
