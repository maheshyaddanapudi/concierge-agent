"""Chat API (spec §4): conversations, POST /chat, SSE stream, HITL resolve."""

import asyncio
import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import SessionDep
from app.models import Conversation, Run
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
        "target_sub_agent_id": str(run.target_sub_agent_id)
        if run.target_sub_agent_id
        else None,
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
async def list_conversations(session: SessionDep) -> list[dict[str, Any]]:
    conversations = list(
        (
            await session.execute(select(Conversation).order_by(Conversation.updated_at.desc()))
        ).scalars()
    )
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "run_count": len(c.runs),
        }
        for c in conversations
    ]


@router.post("/conversations", status_code=201)
async def create_conversation(body: ConversationCreate, session: SessionDep) -> dict[str, Any]:
    conversation = Conversation(title=body.title or "New conversation")
    session.add(conversation)
    await session.commit()
    return {"id": str(conversation.id), "title": conversation.title}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID, session: SessionDep) -> dict[str, Any]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
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
        run = await create_run(
            body.conversation_id, body.message, mode="direct", target_sub_agent_id=agent.id
        )
    else:
        run = await create_run(body.conversation_id, body.message)
    start_run_task(run.id)
    return {"run_id": str(run.id), "conversation_id": str(run.conversation_id)}


class _StreamDone(Exception):
    pass


@router.get("/chat/stream/{run_id}")
async def chat_stream(run_id: UUID, session: SessionDep) -> EventSourceResponse:
    """SSE event stream (spec §7.1 contract): replay + live."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def gen() -> Any:
        history, queue = EVENT_BUS.subscribe(run_id)
        try:
            terminal = False
            for event in history:
                yield {"event": event["type"], "data": json.dumps(event)}
                if _is_terminal(event):
                    terminal = True
            if terminal:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": event["type"], "data": json.dumps(event)}
                if _is_terminal(event):
                    return
        finally:
            EVENT_BUS.unsubscribe(run_id, queue)

    return EventSourceResponse(gen())


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
