"""Memory store API (spec §16.6) — the Memory page's backend.

Every mutating action here is a USER action: creates are `user_stated`,
edits supersede with `user_edited`, deletes are the sanctioned hard path,
review decisions resolve quarantined rows.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update

from app.api.deps import SessionDep
from app.auth import owns_row
from app.memory import MemoryWriteError, hard_delete, recall, remember, supersede
from app.memory.store import list_memories
from app.models import Memory, MemoryEmbedding
from app.schemas.memory import (
    MemoryCreate,
    MemoryOut,
    MemoryPatch,
    MemoryStatusOut,
    RecallOut,
)

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
async def list_all(
    scope: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    source: str | None = None,
    conversation_id: UUID | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
) -> list[Memory]:
    return await list_memories(
        scope=scope,
        kind=kind,
        status=status,
        source=source,
        conversation_id=conversation_id,
        q=q,
        limit=limit,
    )


@router.get("/status", response_model=MemoryStatusOut)
async def memory_status(session: SessionDep) -> MemoryStatusOut:
    status_rows = (
        await session.execute(select(Memory.status, func.count()).group_by(Memory.status))
    ).all()
    kind_rows = (
        await session.execute(select(Memory.kind, func.count()).group_by(Memory.kind))
    ).all()
    by_status: dict[str, int] = {str(r[0]): int(r[1]) for r in status_rows}
    by_kind: dict[str, int] = {str(r[0]): int(r[1]) for r in kind_rows}
    pinned = (
        await session.execute(
            select(func.count()).where(Memory.pinned.is_(True), Memory.status == "active")
        )
    ).scalar_one()
    embeddings = (
        await session.execute(select(func.count()).select_from(MemoryEmbedding))
    ).scalar_one()
    return MemoryStatusOut(
        counts=by_status,
        by_kind=by_kind,
        quarantined=by_status.get("quarantined", 0),
        pinned=int(pinned),
        embeddings=int(embeddings),
    )


@router.get("/recall", response_model=list[RecallOut])
async def recall_endpoint(
    q: str,
    scope: str | None = None,
    kinds: str | None = None,
    conversation_id: UUID | None = None,
    k: int = Query(default=6, le=50),
    floor: float = Query(default=0.0, ge=0.0, le=1.0),
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    hits = await recall(
        q,
        scopes=[scope] if scope else None,
        kinds=kinds.split(",") if kinds else None,
        conversation_id=conversation_id,
        k=k,
        floor=floor,
        as_of=as_of,
        bump_access=False,  # inspection must not distort rehearsal stats
    )
    return [
        {
            "memory": MemoryOut.model_validate(h.memory),
            "score": h.score,
            "relevance": h.relevance,
            "recency": h.recency,
            "importance": h.importance,
        }
        for h in hits
    ]


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_one(memory_id: UUID, session: SessionDep) -> Memory:
    row = await session.get(Memory, memory_id)
    if row is None or not owns_row(row):
        raise HTTPException(404, "memory not found")
    return row


@router.post("", response_model=MemoryOut, status_code=201)
async def create(body: MemoryCreate) -> Memory:
    try:
        row = await remember(
            text=body.text,
            kind=body.kind,
            scope=body.scope,
            source="user_stated",
            conversation_id=body.conversation_id,
            payload=body.payload,
            entity_key=body.entity_key,
            importance=body.importance,
            confidence=1.0,  # the human said it
        )
    except MemoryWriteError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.pinned:
        from app.db import get_session_factory

        async with get_session_factory()() as session:
            fresh = await session.get(Memory, row.id)
            assert fresh is not None
            fresh.pinned = True
            await session.commit()
            await session.refresh(fresh)
            return fresh
    return row


@router.patch("/{memory_id}", response_model=MemoryOut)
async def patch(memory_id: UUID, body: MemoryPatch, session: SessionDep) -> Memory:
    row = await session.get(Memory, memory_id)
    if row is None or not owns_row(row):
        raise HTTPException(404, "memory not found")

    # edit-as-supersede: text changes never mutate history (spec §16.1)
    if body.text is not None and body.text != row.text:
        try:
            new = await supersede(
                memory_id,
                text=body.text,
                source="user_edited",
                importance=body.importance,
            )
        except MemoryWriteError as exc:
            raise HTTPException(409, str(exc)) from exc
        if body.pinned is not None:
            fresh = await session.get(Memory, new.id)
            assert fresh is not None
            fresh.pinned = body.pinned
            await session.commit()
            await session.refresh(fresh)
            return fresh
        return new

    if body.review is not None:
        if row.status != "quarantined":
            raise HTTPException(409, "only quarantined memories take review decisions")
        row.status = "active" if body.review == "approve" else "rejected"
        row.review_note = body.review_note
        if body.review == "reject":
            row.valid_to = datetime.now(UTC)
    if body.pinned is not None:
        row.pinned = body.pinned
    if body.importance is not None:
        row.importance = body.importance
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{memory_id}", status_code=204)
async def delete_one(memory_id: UUID) -> None:
    if not await hard_delete(memory_id):
        raise HTTPException(404, "memory not found")


@router.post("/purge", status_code=204)
async def purge_memories(session: SessionDep) -> None:
    """§8.7 Data purge, memory half: clears the semantic store and embeddings.
    Episodic tables (run_digests, rollups, exemplars) cascade with run purge."""
    await session.execute(sa_delete(MemoryEmbedding))
    # break the self-referential supersession FKs before deleting the rows
    await session.execute(sa_update(Memory).values(supersedes=None, superseded_by=None))
    await session.execute(sa_delete(Memory))
    await session.commit()
