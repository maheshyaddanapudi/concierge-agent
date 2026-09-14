"""Settings API (spec §4, §3.7) + HITL pending queue."""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import Run
from app.settings_store import SettingsValidationError, get_settings, update_settings

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def read_settings(session: SessionDep) -> dict[str, Any]:
    return await get_settings(session)


@router.patch("/settings")
async def patch_settings(updates: dict[str, Any], session: SessionDep) -> dict[str, Any]:
    try:
        return await update_settings(session, updates)
    except SettingsValidationError as exc:
        raise HTTPException(status_code=422, detail="; ".join(exc.errors)) from exc


@router.get("/providers")
async def list_providers_endpoint() -> list[dict[str, Any]]:
    """Read-only provider adapters panel (spec §2.1, §8.7)."""
    from dataclasses import asdict

    from app.llm import list_providers

    return [
        {
            "provider_id": p.provider_id,
            "configured": p.is_configured(),
            "models": [asdict(m) for m in p.list_models()],
        }
        for p in list_providers()
    ]


@router.get("/hitl/pending")
async def hitl_pending(session: SessionDep) -> list[dict[str, Any]]:
    """All currently paused runs across chats (spec §8.7).

    §15: eval runs are excluded — they resolve their own gates under the
    dataset's policy and have no human waiting, so a batch used to fill this
    queue with approvals nobody could meaningfully act on. Ordered, because
    the queue is polled every few seconds and rendered with buttons: an
    unordered result reshuffled them under the operator's cursor.

    §18.8: scoped to the caller. Unscoped, this queue showed every user's
    paused runs — and the decision endpoint it links to was itself unguarded,
    so it was a list of other people's gates with working buttons beside them.
    """
    from app.auth import scope_to_user

    runs = (
        (
            await session.execute(
                scope_to_user(select(Run), Run)
                .where(Run.status == "paused_hitl", Run.is_eval.is_(False))
                .order_by(Run.started_at, Run.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "run_id": str(r.id),
            "conversation_id": str(r.conversation_id),
            "chat_message": r.chat_message,
            "started_at": r.started_at.isoformat(),
        }
        for r in runs
    ]
