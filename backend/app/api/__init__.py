"""API routers (spec §4) — REST, JSON, mounted at /api/v1."""

from fastapi import APIRouter

from app.api import chat, fake_llm, mcp_servers, runs, seed, settings, skills, sub_agents, tools

api_router = APIRouter()
api_router.include_router(mcp_servers.router)
api_router.include_router(tools.router)
api_router.include_router(skills.router)
api_router.include_router(sub_agents.router)
api_router.include_router(chat.router)
api_router.include_router(runs.router)
api_router.include_router(settings.router)
api_router.include_router(seed.router)
api_router.include_router(fake_llm.router)
