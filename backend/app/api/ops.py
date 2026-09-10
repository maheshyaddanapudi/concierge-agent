"""Operator surfaces (M53): retention preview / run-now, the day's spend;
(M54) the fleet — every replica's heartbeat and the connection budget."""

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


@router.get("/replicas")
async def replicas_status() -> dict[str, Any]:
    """M54 (spec §18.9): the fleet as the database sees it — every replica's
    heartbeat, subscriber count and runs in flight, which are live, this
    process's id, and the connection-budget arithmetic against the declared
    Postgres."""
    from datetime import UTC, datetime

    from app import control
    from app.db import connection_budget
    from app.replica import REPLICA_DEAD_AFTER_S, all_replicas, replica_id

    now = datetime.now(UTC)
    rows = await all_replicas()
    return {
        "self": replica_id(),
        "control_listener": control.listener_connected(),
        "dead_after_s": REPLICA_DEAD_AFTER_S,
        "replicas": [
            {
                "replica_id": r.replica_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "heartbeat_at": r.heartbeat_at.isoformat() if r.heartbeat_at else None,
                "subscribers": int(r.subscribers),
                "runs_in_flight": int(r.runs_in_flight),
                "live": bool(
                    r.heartbeat_at and (now - r.heartbeat_at).total_seconds() < REPLICA_DEAD_AFTER_S
                ),
            }
            for r in rows
        ],
        "budget": connection_budget(),
    }
