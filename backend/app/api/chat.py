"""Chat API (spec §4): conversations, POST /chat, SSE stream, HITL resolve."""

import asyncio
import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.api.deps import SessionDep
from app.auth import owns_row, scope_to_user
from app.db import get_session_factory
from app.models import Conversation, Run
from app.orchestrator import admission
from app.orchestrator.context import EVENT_BUS
from app.orchestrator.runner import create_run, resume_run, start_run_task
from app.schemas.common import ApiModel

router = APIRouter(tags=["chat"])


class ConversationCreate(ApiModel):
    title: str | None = None


class ChatRequest(ApiModel):
    conversation_id: UUID | None = None
    message: str
    # optional pin (spec §7.5): the message runs as a 'direct' run against
    # this sub agent instead of going through the orchestrator
    target_sub_agent_id: UUID | None = None
    # §7.5 opt-in, target-only: summarize history into the worker's context
    include_history_summary: bool = False
    include_memories: bool = False
    # §18.2: tag the NEW conversation with a project key (ignored when
    # continuing an existing conversation)
    project: str | None = None


class HitlRequest(ApiModel):
    decision: Literal["approve", "deny"]
    note: str = ""
    # form gates (spec §3.5): {question_id: value}
    answers: dict[str, Any] | None = None


def _run_out(run: Run) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "conversation_id": str(run.conversation_id),
        "chat_message": run.chat_message,
        "status": run.status,
        "orchestrator_mode": run.orchestrator_mode,
        "target_sub_agent_id": str(run.target_sub_agent_id) if run.target_sub_agent_id else None,
        "include_history_summary": run.include_history_summary,
        "include_memories": run.include_memories,
        "final_answer": run.final_answer,
        "answer_ui": run.answer_ui,
        "charts": run.charts,
        "error": run.error,
        "plan": run.plan,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_input_tokens": run.total_input_tokens,
        "total_output_tokens": run.total_output_tokens,
    }


@router.get("/conversations")
async def list_conversations(
    session: SessionDep,
    response: Response,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Newest first, paged (M50): `limit`/`offset`, total in X-Total-Count.
    run_count is an aggregate — before M50 it loaded every run of every
    conversation (the 10× growth in the M49 baseline)."""
    scoped = scope_to_user(select(Conversation), Conversation)
    total = (
        await session.execute(select(func.count()).select_from(scoped.subquery()))
    ).scalar_one()
    counts = (
        select(Run.conversation_id, func.count(Run.id).label("n"))
        .group_by(Run.conversation_id)
        .subquery()
    )
    rows = (
        await session.execute(
            scope_to_user(
                select(Conversation, func.coalesce(counts.c.n, 0))
                .outerjoin(counts, counts.c.conversation_id == Conversation.id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
                .offset(offset),
                Conversation,
            )
        )
    ).all()
    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "run_count": int(n),
        }
        for c, n in rows
    ]


@router.post("/conversations", status_code=201)
async def create_conversation(body: ConversationCreate, session: SessionDep) -> dict[str, Any]:
    from app.auth import current_user_id

    conversation = Conversation(title=body.title or "New conversation", user_id=current_user_id())
    session.add(conversation)
    await session.commit()
    return {"id": str(conversation.id), "title": conversation.title}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID, session: SessionDep) -> dict[str, Any]:
    conversation = (
        await session.execute(
            select(Conversation)
            .options(selectinload(Conversation.runs))  # M50: explicit child load
            .where(Conversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None or not owns_row(conversation):
        raise HTTPException(status_code=404, detail="conversation not found")
    runs = sorted(conversation.runs, key=lambda r: r.started_at)
    messages: list[dict[str, Any]] = []
    for run in runs:
        messages.append({"role": "user", "content": run.chat_message, "run_id": str(run.id)})
        if run.final_answer is not None:
            messages.append(
                {
                    "role": "assistant",
                    "content": run.final_answer,
                    "run_id": str(run.id),
                    "answer_ui": run.answer_ui,
                    "charts": run.charts,
                }
            )
        elif run.status in {"failed", "cancelled"} and run.error:
            # reloaded history mirrors the live view: a run that produced no
            # answer still shows WHY, keeping user→response interleaving
            messages.append(
                {
                    "role": "error",
                    "content": run.error,
                    "run_id": str(run.id),
                }
            )
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "messages": messages,
        "runs": [_run_out(r) for r in runs],
    }


@router.post("/chat", status_code=201)
async def chat(body: ChatRequest, session: SessionDep) -> dict[str, Any]:
    """{conversation_id, message} → run_id (spec §4); the run executes as an
    asyncio task in this process (spec §2)."""
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    if body.include_memories and body.target_sub_agent_id is None:
        raise HTTPException(
            status_code=422,
            detail="include_memories applies only to sub-agent-pinned messages — "
            "the orchestrator injects memory on its own surfaces",
        )
    if body.include_history_summary and body.target_sub_agent_id is None:
        raise HTTPException(
            status_code=422,
            detail="include_history_summary applies only to sub-agent-pinned messages — "
            "the orchestrator always receives conversation history",
        )
    try:
        run = await _create_chat_run(body, session)
    except admission.AtCapacity as exc:
        # M51: shed load explicitly — never an invisible wait; M53: the
        # spend ceiling is the same shape with a 429
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={"Retry-After": str(exc.retry_after_s)},
        ) from exc
    start_run_task(run.id, shed_if_full=True)
    return {"run_id": str(run.id), "conversation_id": str(run.conversation_id)}


async def _create_chat_run(body: ChatRequest, session: Any) -> Run:
    if body.target_sub_agent_id is not None:
        # pinned message (spec §7.5): same gating as /sub-agents/{id}/invoke
        from app.models import SubAgent

        agent = await session.get(SubAgent, body.target_sub_agent_id)
        if agent is None or agent.deleted_at is not None:
            raise HTTPException(status_code=404, detail="target sub agent not found")
        if agent.status != "active":
            raise HTTPException(status_code=409, detail=f"sub agent {agent.name!r} is not active")
        if not agent.direct_exposure:
            raise HTTPException(
                status_code=403,
                detail=f"sub agent {agent.name!r} is not exposed for direct invocation",
            )
        return await create_run(
            body.conversation_id,
            body.message,
            mode="direct",
            target_sub_agent_id=agent.id,
            include_history_summary=body.include_history_summary,
            include_memories=body.include_memories,
            project_key=body.project,
            shed_if_full=True,
        )
    return await create_run(
        body.conversation_id, body.message, project_key=body.project, shed_if_full=True
    )


# M53 wire format (scale-B3): the heartbeat sits inside the tightest load-
# balancer idle default (15 s), every run event carries a monotonic `id:`,
# and a client that reconnects with Last-Event-ID gets only what it missed.
SSE_HEARTBEAT_S = 15.0
SSE_RECONNECT_RETRY_MS = 5000
_TERMINAL = {"completed", "failed", "cancelled"}


def _wire(event: dict[str, Any]) -> dict[str, Any]:
    out = {"event": event["type"], "data": json.dumps(event)}
    if event.get("seq"):
        out["id"] = str(event["seq"])
    return out


def synthesize_terminal_events(run: Run, after: int) -> list[dict[str, Any]]:
    """A run whose events are gone from this process (a deploy, an eviction)
    still resolves for a reconnecting client: the row is the record. The
    sequence continues from the client's Last-Event-ID so idempotent folding
    keeps working."""
    from app.orchestrator.recorder import sse_event

    seq = after
    events: list[dict[str, Any]] = []

    def ev(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal seq
        seq += 1
        event = sse_event(event_type, run.id, payload)
        event["seq"] = seq
        event["replayed_from"] = "record"
        events.append(event)

    if run.status == "completed":
        ev("run_status", {"status": "completed"})
        ev(
            "done",
            {
                "answer": run.final_answer or "",
                "tokens": {
                    "input_tokens": run.total_input_tokens,
                    "output_tokens": run.total_output_tokens,
                },
            },
        )
    elif run.status == "failed":
        ev("error", {"message": run.error or "run failed"})
        ev("run_status", {"status": "failed"})
    elif run.status == "cancelled":
        ev("run_status", {"status": "cancelled"})
    elif run.status == "paused_hitl":
        ev("run_status", {"status": "paused_hitl"})
    return events


async def stream_run_events(run_id: UUID, after: int = 0) -> Any:
    """The event generator behind /chat/stream: replay after `after`, then
    live, with a heartbeat every SSE_HEARTBEAT_S. While this process drains
    (M53) a stream it cannot serve — the run is not executing here — is
    closed politely with a `reconnect` hint; a run executing here streams
    on until its terminal event."""
    from app.orchestrator import admission
    from app.orchestrator.runner import RUNNING_TASKS

    history, queue = EVENT_BUS.subscribe(run_id, after=after)
    try:
        if not history:
            if EVENT_BUS.is_done(run_id):
                return  # the client already holds everything
            if EVENT_BUS.last_seq(run_id) == 0:
                async with get_session_factory()() as session:
                    run = await session.get(Run, run_id)
                if run is not None and run.status in _TERMINAL | {"paused_hitl"}:
                    for event in synthesize_terminal_events(run, after):
                        yield _wire(event)
                    if run.status in _TERMINAL:
                        return
        for event in history:
            yield _wire(event)
            if _is_terminal(event):
                return
        while True:
            if not admission.accepting() and run_id not in RUNNING_TASKS:
                yield {
                    "event": "reconnect",
                    "data": json.dumps(
                        {"reason": "draining", "retry_after_ms": SSE_RECONNECT_RETRY_MS}
                    ),
                    "retry": SSE_RECONNECT_RETRY_MS,
                }
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_S)
            except TimeoutError:
                yield {"event": "ping", "data": "{}"}
                continue
            yield _wire(event)
            if _is_terminal(event):
                return
    finally:
        EVENT_BUS.unsubscribe(run_id, queue)


@router.get("/chat/stream/{run_id}")
async def chat_stream(
    run_id: UUID,
    request: Request,
    after: int | None = Query(default=None, ge=0),
) -> EventSourceResponse:
    """SSE event stream (spec §7.1 contract): replay + live. M50 (arch-C1):
    the existence check uses a short-lived session released BEFORE the
    stream opens — an open tab holds no pooled connection. M53: resumes
    from `Last-Event-ID` (EventSource sends it on every reconnect) or the
    `after` query for clients that cannot set headers."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
    last = request.headers.get("last-event-id", "")
    start = after if isinstance(after, int) else (int(last) if last.isdigit() else 0)
    return EventSourceResponse(
        stream_run_events(run_id, after=start),
        ping=60,  # sse-starlette's comment ping is only a backstop; `ping` events carry the beat
    )


def _is_terminal(event: dict[str, Any]) -> bool:
    if event.get("type") == "done":
        return True
    return event.get("type") == "run_status" and event.get("payload", {}).get("status") in {
        "failed",
        "cancelled",
    }


@router.post("/runs/{run_id}/hitl")
async def resolve_hitl(run_id: UUID, body: HitlRequest) -> dict[str, Any]:
    try:
        await resume_run(run_id, body.decision, body.note, body.answers)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "resuming", "decision": body.decision}
