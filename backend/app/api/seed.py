"""Idempotent seed reload endpoint (spec §4)."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.seed.loader import seed_all

router = APIRouter(tags=["seed"])


@router.post("/seed/reload")
async def reload_seed(session: SessionDep) -> dict[str, Any]:
    summary = await seed_all(session)
    return {"status": "ok", **summary}
