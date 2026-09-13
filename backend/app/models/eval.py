"""Eval storage (spec §15 — milestone M32): datasets of graded cases run
admin-direct against a skill or sub agent; every result links the ordinary
Run that produced the answer."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# R7.3: every FK in this module cascades, and none of them was indexed — so
# reading a dataset's cases, a run's results, or deleting either, scanned the
# whole table.


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(16))  # 'skill' | 'sub_agent'
    target_id: Mapped[uuid.UUID] = mapped_column()
    # §15: whether a human gate reached during this dataset's runs may be
    # cleared by the harness. Default FALSE: an uploaded case used to drive a
    # gated workflow — including an irreversible one — to completion with the
    # approval granted by a log line and no human decision recorded anywhere.
    allow_hitl_autoapprove: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalCase(Base):
    __tablename__ = "eval_cases"
    __table_args__ = (Index("eval_cases_dataset_idx", "dataset_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE")
    )
    input: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text, default="")
    judge_notes: Mapped[str] = mapped_column(Text, default="")
    grader: Mapped[str] = mapped_column(String(16), default="llm_judge")
    position: Mapped[int] = mapped_column(Integer, default=0)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (Index("eval_runs_dataset_idx", "dataset_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed|failed
    # reproducibility (spec §15): settings + target definition at run time
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    error_cases: Mapped[int] = mapped_column(Integer, default=0)
    langsmith_url: Mapped[str | None] = mapped_column(String(512), default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class EvalResult(Base):
    __tablename__ = "eval_results"
    __table_args__ = (
        # eval_run_id is not on the SCHEMA-TODO list but is the same gap, and
        # the one every results read goes through
        Index("eval_results_eval_run_idx", "eval_run_id"),
        Index("eval_results_case_idx", "case_id"),
        Index("eval_results_run_idx", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_cases.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(16), default="graded")  # graded | error
    passed: Mapped[bool] = mapped_column(default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    grader_reason: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
