"""Run/step recording (spec §3.6) + trace emission (spec §10).

Every step start/finish writes a run_steps row, a structlog event with the
shared label set, Prometheus metrics, an OTel span, and the matching SSE
events. Token totals roll up onto the run.
"""

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import update

from app import obs
from app.db import get_session_factory
from app.models import Run, RunStep
from app.orchestrator.context import EVENT_BUS
from app.sanitize import sanitize_error

logger = structlog.get_logger("run")


class StepFailed(Exception):
    """The exception a failed step records on its span. Steps fail with a
    sanitized message, not an exception object, so the OTel
    `record_exception` path needs something to carry it."""


def sse_event(event_type: str, run_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "run_id": str(run_id),
        "ts": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


class RunRecorder:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self._starts: dict[UUID, float] = {}
        self._labels: dict[UUID, dict[str, Any]] = {}
        self._tracer = obs.get_tracer()
        self._spans: dict[UUID, Any] = {}
        # the run's clock starts with its first recorder; the failure path
        # builds a SECOND recorder for the same run and must not reset it
        obs.mark_run_started(run_id)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "run_status":
            status = str(payload.get("status") or "")
            # every terminal path emits this — completed, failed, cancelled,
            # the wall clock and a peer's cancel intent alike. `completed` is
            # already timed inline where the run record is written; the rest
            # had no RUN_DURATION series at all, which is exactly the half an
            # incident needs.
            if status in obs.RECORDER_TIMED_STATUSES:
                obs.observe_run_duration(self.run_id, status)
            elif status in obs.TERMINAL_RUN_STATUSES:
                obs.forget_run_timer(self.run_id)  # timed elsewhere; drop the record
        EVENT_BUS.emit(self.run_id, sse_event(event_type, self.run_id, payload))

    async def start_step(
        self,
        step_type: str,
        *,
        tier: str,
        kind: str | None = None,
        source: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
        node_id: str | None = None,
        sub_agent_id: str | None = None,
        parent_step_id: UUID | None = None,
        model: str | None = None,
        effort: str | None = None,
        input: dict[str, Any] | None = None,
        emit_dispatch: bool = False,
        entity_version: int | None = None,
        entity_hash: str | None = None,
        model_params: dict[str, Any] | None = None,
    ) -> UUID:
        async with get_session_factory()() as session:
            step = RunStep(
                run_id=self.run_id,
                parent_step_id=parent_step_id,
                sub_agent_id=UUID(sub_agent_id) if sub_agent_id else None,
                node_id=node_id,
                step_type=step_type,
                input=input,
                model=model,
                # the name at run time and the params the step ran with —
                # on the row, so a trace never resolves either live
                entity_name=entity_name,
                model_params=model_params,
                # the entity's version pinned into the record (a tool's
                # schema version and hash): the trace reads against the
                # registry as it was when the step ran
                entity_version=entity_version,
                entity_hash=entity_hash,
                status="running",
            )
            session.add(step)
            await session.commit()
            step_id = step.id
        self._starts[step_id] = time.monotonic()
        from app.orchestrator.context import get_run_context

        ctx = get_run_context()
        if ctx is not None:
            # the mode the run executes under, onto its timing record: the
            # terminal paths the runner does not time itself label their
            # RUN_DURATION sample from it
            obs.mark_run_started(self.run_id, ctx.mode)
            if entity_id:
                # retrieval pin (spec §7.4): entities used in this run stay
                # visible in ranked catalogs for the rest of the run
                ctx.pinned_ids.add(str(entity_id))
        labels = obs.label_set(
            run_id=str(self.run_id),
            step_id=str(step_id),
            tier=tier,
            kind=kind,
            source=source,
            entity_id=entity_id,
            entity_name=entity_name,
            model=model,
            effort=effort,
            status="running",
        )
        self._labels[step_id] = labels
        logger.info("step_start", step_type=step_type, **labels)
        # the recorder already computes the step tree (`parent_step_id`); the
        # tracer never saw it, so every span was a ROOT span and the trace
        # panel was flat. Start the child inside the parent's context — when
        # the parent span is still open on this recorder — so the nesting the
        # row records is the nesting the trace shows.
        parent_span = self._spans.get(parent_step_id) if parent_step_id else None
        span = self._tracer.start_span(
            f"{step_type}:{entity_name or node_id or tier}",
            context=(
                otel_trace.set_span_in_context(parent_span) if parent_span is not None else None
            ),
        )
        for key, value in labels.items():
            if value is not None:
                span.set_attribute(f"concierge.{key}", str(value))
        # span attributes, not metric labels: the §10 label set (and its
        # cardinality) stays as specified, the span still names the version
        if entity_version is not None:
            span.set_attribute("concierge.entity_version", int(entity_version))
        if entity_hash:
            span.set_attribute("concierge.entity_hash", entity_hash)
        self._spans[step_id] = span
        # live activity feed (spec §7.1): every step transition, so the chat
        # can show what the run is doing right now without exposing payloads
        self.emit(
            "activity",
            {
                "step_id": str(step_id),
                "parent_step_id": str(parent_step_id) if parent_step_id else None,
                "step_type": step_type,
                "tier": tier,
                "kind": kind,
                "entity_name": entity_name,
                "node_id": node_id,
                "status": "running",
            },
        )
        if emit_dispatch:
            self.emit(
                "dispatch_start",
                {
                    "step_id": str(step_id),
                    "tier": tier,
                    "kind": kind,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                },
            )
        return step_id

    async def finish_step(
        self,
        step_id: UUID,
        *,
        status: str = "completed",
        output: dict[str, Any] | None = None,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        emit_dispatch: bool = False,
    ) -> None:
        duration_ms = int((time.monotonic() - self._starts.pop(step_id, time.monotonic())) * 1000)
        labels = self._labels.pop(step_id, {})
        labels.update(
            {
                "status": status,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )
        async with get_session_factory()() as session:
            step = await session.get(RunStep, step_id)
            if step is not None:
                step.status = status
                step.output = output
                step.error = sanitize_error(error)  # M52: one sanitizer before persistence
                step.input_tokens = input_tokens
                step.output_tokens = output_tokens
                step.finished_at = datetime.now(UTC)
                await session.commit()
            if input_tokens or output_tokens:
                # M51: atomic in-database increment (the totals feed the ambient
                # budget — a lost update under-counts spend)
                await session.execute(
                    update(Run)
                    .where(Run.id == self.run_id)
                    .values(
                        total_input_tokens=Run.total_input_tokens + input_tokens,
                        total_output_tokens=Run.total_output_tokens + output_tokens,
                    )
                )
                await session.commit()
        logger.info("step_finish", **labels)
        # M53: the §10 label set's low-cardinality members on every series
        dims = {
            "tier": str(labels.get("tier") or "orchestrator"),
            "kind": str(labels.get("kind") or "-"),
            "source": str(labels.get("source") or "-"),
            "model": str(labels.get("model") or "-"),
            "effort": str(labels.get("effort") or "-"),
        }
        tier, kind, source = dims["tier"], dims["kind"], dims["source"]
        obs.STEPS_TOTAL.labels(**dims, status=status).inc()
        obs.STEP_DURATION.labels(**dims).observe(duration_ms / 1000)
        if input_tokens:
            obs.STEP_TOKENS.labels(**dims, direction="input").observe(input_tokens)
        if output_tokens:
            obs.STEP_TOKENS.labels(**dims, direction="output").observe(output_tokens)
        if status == "failed":
            obs.ERRORS_TOTAL.labels(tier=tier, kind=kind, source=source).inc()
            self.emit("error", {"step_id": str(step_id), "message": error or "step failed"})
        span = self._spans.pop(step_id, None)
        if span is not None:
            span.set_attribute("concierge.status", status)
            span.set_attribute("concierge.duration_ms", duration_ms)
            # the §10 label set is stamped at START, when the counts are
            # necessarily 0 — without this every span reported a step that
            # spent no tokens, whatever it actually spent
            span.set_attribute("concierge.input_tokens", int(input_tokens))
            span.set_attribute("concierge.output_tokens", int(output_tokens))
            if status == "failed":
                # a failed step used to end its span UNSET, so a trace backend
                # showed no error and carried no message to read
                message = sanitize_error(error) or "step failed"
                span.set_status(Status(StatusCode.ERROR, message))
                span.record_exception(StepFailed(message))
            span.end()
        self.emit("activity", {"step_id": str(step_id), "status": status})
        if emit_dispatch:
            self.emit(
                "dispatch_end",
                {
                    "step_id": str(step_id),
                    "tier": labels.get("tier"),
                    "kind": labels.get("kind"),
                    "entity_id": labels.get("entity_id"),
                    "entity_name": labels.get("entity_name"),
                    "status": status,
                },
            )

    async def record_route(
        self,
        *,
        capability: dict[str, Any],
        rung: str,
        resolved_to: dict[str, Any],
        kind: str | None = None,
        source: str | None = None,
    ) -> None:
        """The ladder is deterministic and logged as a `route` step (spec §7.1).
        The definition version the ladder resolved rides on the step when
        `resolved_to` carries it (a Resolution.as_route())."""
        step_id = await self.start_step(
            "route",
            tier="orchestrator",
            kind=kind,
            source=source,
            entity_id=resolved_to.get("entity_id"),
            entity_name=resolved_to.get("entity_name"),
            input={"capability": capability},
            entity_version=resolved_to.get("definition_version"),
            entity_hash=resolved_to.get("definition_hash"),
        )
        await self.finish_step(step_id, output={"rung": rung, "resolved_to": resolved_to})
        self.emit(
            "route",
            {"capability": capability, "rung": rung, "resolved_to": resolved_to},
        )
