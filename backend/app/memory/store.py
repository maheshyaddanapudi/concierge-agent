"""L2 semantic store — writes (spec §16.1/16.2).

Rules enforced here, not in prompts:
- provenance is mandatory on machine writes (extracted/inferred/hitl_note ⇒ run_id)
- extracted/inferred instruction-kind memories always land quarantined; the
  memory.remember TOOL quarantines instruction-kind too (model-mediated text is
  an injection surface — spec §16.4); only the UI/API with source='user_stated'
  activates an instruction directly
- pipelines never hard-delete: supersede/expire only; hard delete is a
  user/purge action
- supersession is append-only and guarded (`WHERE superseded_at IS NULL`)
- the admission gate is deterministic code (confidence floor, length bounds,
  near-duplicate drop) — write policy is the security boundary (research 03 §5)
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory
from app.models import Memory, MemoryEmbedding

logger = structlog.get_logger("memory")

KINDS = {"fact", "preference", "entity", "relation", "instruction"}
SCOPES = {"global", "conversation"}
SOURCES = {"extracted", "user_stated", "user_edited", "hitl_note", "inferred"}
MACHINE_SOURCES = {"extracted", "inferred", "hitl_note"}

# admission-gate constants (spec §16.2; deliberate constants, not settings —
# the gate must not be loosened by a runtime toggle)
GATE_MIN_CONFIDENCE = 0.5
GATE_MIN_CHARS = 8
GATE_MAX_CHARS = 600
GATE_DUP_COSINE = 0.95


class MemoryWriteError(ValueError):
    """A write violates a §16 rule (bad kind/scope/source, missing provenance,
    double supersede…)."""


@dataclass
class Candidate:
    """An extraction candidate entering the admission gate."""

    text: str
    kind: str
    scope: str = "global"
    conversation_id: UUID | None = None
    payload: dict[str, Any] | None = None
    entity_key: str | None = None
    importance: int = 5
    confidence: float = 0.7
    valid_from: datetime | None = None


def _validate(kind: str, scope: str, source: str) -> None:
    errors = []
    if kind not in KINDS:
        errors.append(f"kind must be one of {sorted(KINDS)}")
    if scope not in SCOPES:
        errors.append(f"scope must be one of {sorted(SCOPES)}")
    if source not in SOURCES:
        errors.append(f"source must be one of {sorted(SOURCES)}")
    if errors:
        raise MemoryWriteError("; ".join(errors))


async def active_model_key() -> str | None:
    """The embedding side-table key: 'provider:model@dims' (spec §16.1)."""
    from app.registry_cache import get_cache

    model = await get_cache().setting("embedding_model")
    if not model:
        return None
    try:
        from app.llm import get_embeddings

        probe = await get_embeddings(str(model), ["dims probe"])
        return f"{model}@{len(probe[0])}"
    except Exception as exc:  # noqa: BLE001 — degrade to lexical-only
        logger.warning("memory_model_key_failed", error=str(exc))
        return None


async def _embed_ref(session: AsyncSession, ref_id: UUID, table_ref: str, text: str) -> None:
    """Best-effort write-through embedding (never fails the save)."""
    try:
        from app.llm import get_embeddings
        from app.registry_cache import get_cache

        model = await get_cache().setting("embedding_model")
        if not model:
            return
        vec = (await get_embeddings(str(model), [text]))[0]
        key = f"{model}@{len(vec)}"
        existing = await session.get(MemoryEmbedding, (ref_id, table_ref, key))
        if existing is None:
            session.add(
                MemoryEmbedding(ref_id=ref_id, table_ref=table_ref, model_key=key, embedding=vec)
            )
        else:
            existing.embedding = vec
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_embed_failed", ref=str(ref_id), error=str(exc))


async def remember(
    *,
    text: str,
    kind: str,
    scope: str = "global",
    source: str,
    conversation_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    entity_key: str | None = None,
    importance: int = 5,
    confidence: float = 0.7,
    valid_from: datetime | None = None,
    run_id: UUID | None = None,
    step_id: UUID | None = None,
    supersedes: UUID | None = None,
    via_tool: bool = False,
    session: AsyncSession | None = None,
) -> Memory:
    """Insert one memory row under the §16.2 rules. Raises MemoryWriteError."""
    _validate(kind, scope, source)
    if source in MACHINE_SOURCES and run_id is None:
        raise MemoryWriteError(f"source '{source}' requires provenance (run_id)")
    if scope == "conversation" and conversation_id is None:
        raise MemoryWriteError("scope 'conversation' requires conversation_id")
    text = " ".join(text.split())
    if not text:
        raise MemoryWriteError("text must not be empty")

    status = "active"
    if kind == "instruction" and (source in {"extracted", "inferred"} or via_tool):
        status = "quarantined"  # behavior-changing writes gate through review

    row = Memory(
        text=text,
        kind=kind,
        scope=scope,
        source=source,
        status=status,
        conversation_id=conversation_id,
        payload=payload,
        entity_key=entity_key,
        importance=max(1, min(10, importance)),
        confidence=max(0.0, min(1.0, confidence)),
        run_id=run_id,
        step_id=step_id,
        supersedes=supersedes,
    )
    if valid_from is not None:
        row.valid_from = valid_from

    async def _write(sess: AsyncSession) -> Memory:
        sess.add(row)
        await sess.flush()
        await _embed_ref(sess, row.id, "memories", row.text)
        await sess.commit()
        await sess.refresh(row)
        return row

    if session is not None:
        result = await _write(session)
    else:
        async with get_session_factory()() as sess:
            result = await _write(sess)
    logger.info(
        "memory_write",
        tier="memory",
        kind=kind,
        source=source,
        status=result.status,
        memory_id=str(result.id),
        run_id=str(run_id) if run_id else None,
    )
    _notify_invalidate()
    return result


async def supersede(
    old_id: UUID,
    *,
    text: str,
    source: str,
    run_id: UUID | None = None,
    step_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    importance: int | None = None,
    confidence: float | None = None,
    valid_from: datetime | None = None,
) -> Memory:
    """Append-only replacement (spec §16.1): insert the new row, close the old
    one bi-temporally in the same transaction. Never deletes."""
    async with get_session_factory()() as session:
        old = await session.get(Memory, old_id)
        if old is None:
            raise MemoryWriteError(f"memory {old_id} not found")
        if old.superseded_at is not None:
            raise MemoryWriteError(f"memory {old_id} is already superseded")
        _validate(old.kind, old.scope, source)
        if source in MACHINE_SOURCES and run_id is None:
            raise MemoryWriteError(f"source '{source}' requires provenance (run_id)")

        now = datetime.now(UTC)
        effective_from = valid_from or now
        new = Memory(
            text=" ".join(text.split()),
            kind=old.kind,
            scope=old.scope,
            conversation_id=old.conversation_id,
            payload=payload if payload is not None else old.payload,
            entity_key=old.entity_key,
            importance=importance if importance is not None else old.importance,
            confidence=confidence if confidence is not None else old.confidence,
            source=source,
            status="active" if old.status in {"active", "expired"} else old.status,
            run_id=run_id,
            step_id=step_id,
            supersedes=old.id,
            pinned=old.pinned,
            half_life_days=old.half_life_days,
        )
        new.valid_from = effective_from
        session.add(new)
        await session.flush()
        # guarded close — no double-supersede even under concurrency
        closed = await session.execute(
            update(Memory)
            .where(Memory.id == old.id, Memory.superseded_at.is_(None))
            .values(
                superseded_at=now,
                superseded_by=new.id,
                valid_to=effective_from,
                status="superseded",
            )
        )
        if int(getattr(closed, "rowcount", 0) or 0) != 1:
            raise MemoryWriteError(f"memory {old_id} was superseded concurrently")
        await _embed_ref(session, new.id, "memories", new.text)
        await session.commit()
        await session.refresh(new)
    logger.info(
        "memory_supersede",
        tier="memory",
        old_id=str(old_id),
        new_id=str(new.id),
        source=source,
    )
    _notify_invalidate()
    return new


async def forget(memory_id: UUID) -> bool:
    """Soft-retire (spec §16.4): status='expired', validity closed. The row
    stays for audit; hard delete is a UI/purge action."""
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        result = await session.execute(
            update(Memory)
            .where(Memory.id == memory_id, Memory.status.in_(("active", "quarantined")))
            .values(status="expired", valid_to=now)
        )
        await session.commit()
    if int(getattr(result, "rowcount", 0) or 0) == 1:
        logger.info("memory_forget", tier="memory", memory_id=str(memory_id))
        _notify_invalidate()
        return True
    return False


async def hard_delete(memory_id: UUID) -> bool:
    """User/purge-only physical delete (spec §16.1)."""
    async with get_session_factory()() as session:
        row = await session.get(Memory, memory_id)
        if row is None:
            return False
        # unlink chain references so FK constraints allow the delete
        await session.execute(
            update(Memory).where(Memory.supersedes == memory_id).values(supersedes=None)
        )
        await session.execute(
            update(Memory).where(Memory.superseded_by == memory_id).values(superseded_by=None)
        )
        from sqlalchemy import delete as sa_delete

        await session.execute(
            sa_delete(MemoryEmbedding).where(
                MemoryEmbedding.ref_id == memory_id, MemoryEmbedding.table_ref == "memories"
            )
        )
        await session.delete(row)
        await session.commit()
    logger.info("memory_hard_delete", tier="memory", memory_id=str(memory_id))
    _notify_invalidate()
    return True


async def gate_candidates(
    candidates: list[Candidate],
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """Deterministic admission gate (spec §16.2). Returns (accepted, dropped
    with reasons). Near-duplicate detection uses embeddings when available,
    normalized-text equality otherwise."""
    accepted: list[Candidate] = []
    dropped: list[tuple[Candidate, str]] = []

    seen_texts: set[str] = set()
    for cand in candidates:
        text = " ".join(cand.text.split())
        norm = text.lower()
        if cand.kind not in KINDS or cand.scope not in SCOPES:
            dropped.append((cand, "invalid kind/scope"))
            continue
        if cand.confidence < GATE_MIN_CONFIDENCE:
            dropped.append((cand, f"confidence {cand.confidence:.2f} < {GATE_MIN_CONFIDENCE}"))
            continue
        if not (GATE_MIN_CHARS <= len(text) <= GATE_MAX_CHARS):
            dropped.append((cand, f"length {len(text)} outside bounds"))
            continue
        if norm in seen_texts:
            dropped.append((cand, "duplicate within batch"))
            continue
        # near-duplicate vs the ACTIVE store
        dup = await _near_duplicate(text, cand.scope, cand.kind, cand.conversation_id)
        if dup is not None:
            dropped.append((cand, f"near-duplicate of {dup}"))
            continue
        seen_texts.add(norm)
        cand.text = text
        accepted.append(cand)
    if dropped:
        logger.info(
            "memory_gate_dropped",
            tier="memory",
            dropped=len(dropped),
            reasons=[r for _, r in dropped],
        )
    return accepted, dropped


async def _near_duplicate(
    text: str, scope: str, kind: str, conversation_id: UUID | None
) -> UUID | None:
    from app.memory.rank import recall

    hits = await recall(
        text,
        scopes=[scope],
        kinds=[kind],
        conversation_id=conversation_id,
        k=1,
        floor=0.0,
        bump_access=False,
    )
    if not hits:
        return None
    top = hits[0]
    if top.relevance >= GATE_DUP_COSINE:
        return top.memory.id
    # lexical fallback: exact normalized match
    if top.memory.text.lower() == text.lower():
        return top.memory.id
    return None


async def list_memories(
    *,
    scope: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    source: str | None = None,
    conversation_id: UUID | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[Memory]:
    async with get_session_factory()() as session:
        stmt = select(Memory).order_by(Memory.recorded_at.desc()).limit(limit)
        if scope:
            stmt = stmt.where(Memory.scope == scope)
        if kind:
            stmt = stmt.where(Memory.kind == kind)
        if status:
            stmt = stmt.where(Memory.status == status)
        if source:
            stmt = stmt.where(Memory.source == source)
        if conversation_id:
            stmt = stmt.where(Memory.conversation_id == conversation_id)
        if q:
            stmt = stmt.where(Memory.text.ilike(f"%{q}%"))
        return list((await session.execute(stmt)).scalars())


def _notify_invalidate() -> None:
    """Fire the §7.3 NOTIFY discipline for the memory store (cache-hint only;
    tables are the truth). Best-effort by design."""
    try:
        from app.registry_cache import get_cache

        cache = get_cache()
        notify = getattr(cache, "notify_memory_dirty", None)
        if callable(notify):  # pragma: no cover - wired when a memory cache exists
            notify()
    except Exception:  # noqa: BLE001, S110 - invalidation must never fail a write
        pass
