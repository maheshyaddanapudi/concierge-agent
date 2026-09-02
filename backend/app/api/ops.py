"""Operator surfaces (M53): retention preview / run-now, and the day's spend."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.settings_store import get_settings

router = APIRouter(tags=["ops"])


@router.get("/retention")
async def retention_status(session: SessionDep) -> dict[str, Any]:
    """Per table: its gate, its window and how many rows a purge would
    delete right now (counted whether or not the gate is on)."""
    from app.retention import RETENTION_GATES, RETENTION_TABLES, RETENTION_WINDOWS, eligible_counts

    settings = await get_settings(session)
    eligible = await eligible_counts()
    return {
        "tables": [
            {
                "table": table,
                "enabled": bool(settings[RETENTION_GATES[table]]),
                "days": int(settings[RETENTION_WINDOWS[table]]),
                "eligible": eligible[table],
            }
            for table in RETENTION_TABLES
        ]
    }


@router.post("/retention/run")
async def retention_run_now() -> dict[str, Any]:
    """Run every purge now — each still answers to its own gate."""
    from app.retention import run_retention

    deleted = await run_retention()
    out: dict[str, Any] = {"deleted": deleted}
    if not deleted:
        out["skipped"] = "another replica holds the retention lock"
    return out


@router.get("/spend")
async def spend(session: SessionDep) -> dict[str, Any]:
    from app.cost import spend_today

    settings = await get_settings(session)
    return await spend_today(settings, fresh=True)
