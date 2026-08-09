"""conversations / runs / run_steps (spec §3.6)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runs: Mapped[list["Run"]] = relationship(back_populates="conversation", lazy="selectin")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    chat_message: Mapped[str] = mapped_column(Text)
    plan: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    # 'running' | 'paused_hitl' | 'completed' | 'failed' | 'cancelled'
    status: Mapped[str] = mapped_column(String(16), default="running")
    # 'graph' | 'agentic' | 'direct' (spec §7.5)
    orchestrator_mode: Mapped[str] = mapped_column(String(16), default="graph")
    # set only on 'direct' runs: the sub agent the user pinned (spec §7.5)
    target_sub_agent_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # §7.5 opt-in: summarize conversation history into the worker's context
    include_history_summary: Mapped[bool] = mapped_column(default=False)
    final_answer: Mapped[str | None] = mapped_column(Text, default=None)
    # the formatter's structured artifact (spec §7.1 answer_ui) — carries its
    # own presentation + coverage so history renders by run-time facts
    answer_ui: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    # chart specs from the render_chart native tool — formatter-independent
    charts: Mapped[list[Any] | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped[Conversation] = relationship(back_populates="runs")
    steps: Mapped[list["RunStep"]] = relationship(
        back_populates="run", lazy="selectin", order_by="RunStep.started_at"
    )


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    parent_step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("run_steps.id"), default=None
    )
    sub_agent_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    node_id: Mapped[str | None] = mapped_column(String(255), default=None)
    # 'plan' | 'route' | 'skill' | 'hitl' | 'tool_call' | 'aggregate'
    step_type: Mapped[str] = mapped_column(String(16))
    input: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    model: Mapped[str | None] = mapped_column(String(255), default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    run: Mapped[Run] = relationship(back_populates="steps")
