"""Memory layer tables (spec §16.1).

Invariants enforced here and in app/memory/store.py: pipelines never
hard-delete (supersede/expire only — hard delete is a user/purge action);
supersession is append-only; `status='active'` rows form the current view;
memory rows are not registry rows (§4 unchanged).
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "memories_current_scope_kind_idx",
            "scope",
            "kind",
            postgresql_where="status = 'active'",
        ),
        Index("memories_fts_idx", "fts", postgresql_using="gin"),
        Index("memories_conversation_idx", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 'global' | 'conversation' ('project' reserved for multi-user)
    scope: Mapped[str] = mapped_column(String(16), default="global")
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), default=None
    )
    # 'fact' | 'preference' | 'entity' | 'relation' | 'instruction'
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    # structured form: relation {subject_entity_id, predicate, object_*};
    # preference {key, value}
    payload: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    # what single-valued fact this is "about" — reconciliation joins on it
    entity_key: Mapped[str | None] = mapped_column(String(255), default=None)
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1..10, write-time
    confidence: Mapped[float] = mapped_column(Float, default=0.7)  # 0..1
    # 'extracted' | 'user_stated' | 'user_edited' | 'hitl_note' | 'inferred'
    source: Mapped[str] = mapped_column(String(16))
    # 'active' | 'quarantined' | 'superseded' | 'expired' | 'rejected'
    status: Mapped[str] = mapped_column(String(16), default="active")
    # bi-temporal: event time (when true in the world) …
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # … and ingestion time (when the system knew)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    supersedes: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memories.id"), default=None)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memories.id"), default=None)
    # provenance — mandatory on machine writes (enforced in the service)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), default=None
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # rehearsal bookkeeping (decay operates on ACCESS recency)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(default=False)  # always injected + decay-immune
    half_life_days: Mapped[float | None] = mapped_column(Float, default=None)
    # review-queue note (quarantine approve/reject)
    review_note: Mapped[str | None] = mapped_column(Text, default=None)
    fts: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )


class MemoryEmbedding(Base):
    """Untyped-vector side-table keyed by (memory row, model) — the
    provider-agnostic dimension strategy (spec §16.1): a model switch
    re-embeds in the background and flips, old and new coexisting."""

    __tablename__ = "memory_embeddings"
    __table_args__ = (Index("memory_embeddings_model_idx", "model_key"),)

    # references memories.id OR run_digests.id — the `table_ref` column says which
    ref_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    table_ref: Mapped[str] = mapped_column(String(24), primary_key=True)  # 'memories'|'run_digests'
    model_key: Mapped[str] = mapped_column(String(255), primary_key=True)  # provider:model@dims
    embedding: Mapped[Any] = mapped_column(Vector(None))
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MemoryEntity(Base):
    __tablename__ = "memory_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(64), default=None)
    aliases: Mapped[list[Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryEntityLink(Base):
    __tablename__ = "memory_entity_links"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory_entities.id", ondelete="CASCADE"), primary_key=True
    )


class RunDigest(Base):
    """L1 episodic retrieval unit (spec §16.2/§16.7): one row per completed
    run (kind='run'), or a synthetic per-conversation compaction of old
    run-digests (kind='period', run_id NULL, covers_from..covers_to)."""

    __tablename__ = "run_digests"
    __table_args__ = (Index("run_digests_fts_idx", "fts", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), unique=True, default=None
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16), default="run")  # 'run' | 'period'
    covers_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    covers_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    text: Mapped[str] = mapped_column(Text)
    # {status, mode, rungs: [], hitl: [{status, note}], stopped, corrected,
    #  input_tokens, output_tokens, duration_ms}
    signals: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fts: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )


class ConversationRollup(Base):
    """L1 sense-making summary per conversation — a complement to run-level
    digests, never the primary retrieval index (spec §16.2)."""

    __tablename__ = "conversation_rollups"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    text: Mapped[str] = mapped_column(Text)
    runs_covered: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanExemplar(Base):
    """L3 procedural memory: a positively-signaled plan/todo trace keyed by
    task text, with the ExpeL vote lifecycle (spec §16.5)."""

    __tablename__ = "plan_exemplars"
    __table_args__ = (Index("plan_exemplars_fts_idx", "fts", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    task_text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))  # 'graph' | 'agentic'
    # graph: the plan entries json; agentic: the capability sequence
    trace: Mapped[dict[str, Any]] = mapped_column()
    votes: Mapped[int] = mapped_column(Integer, default=1)  # retire at 0
    status: Mapped[str] = mapped_column(String(16), default="active")  # 'active'|'retired'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fts: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', task_text)", persisted=True),
        nullable=True,
    )


class RoutingStat(Base):
    """L3: per-capability outcome statistics, consolidation-refreshed."""

    __tablename__ = "routing_stats"

    # rung + entity identify a capability row ('direct_skill:<uuid>' etc.)
    capability_key: Mapped[str] = mapped_column(String(320), primary_key=True)
    rung: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    entity_name: Mapped[str | None] = mapped_column(String(255), default=None)
    runs_total: Mapped[int] = mapped_column(Integer, default=0)
    runs_completed: Mapped[int] = mapped_column(Integer, default=0)
    runs_failed: Mapped[int] = mapped_column(Integer, default=0)
    hitl_denied: Mapped[int] = mapped_column(Integer, default=0)
    mean_input_tokens: Mapped[float] = mapped_column(Float, default=0.0)
    mean_output_tokens: Mapped[float] = mapped_column(Float, default=0.0)
    mean_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
