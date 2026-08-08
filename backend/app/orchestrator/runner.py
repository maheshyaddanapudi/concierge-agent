"""Run lifecycle (spec §7, §3.6): runs execute as asyncio tasks inside the
single FastAPI process — no broker, no queue. HITL pause/resume rides the
LangGraph Postgres checkpointer; cancellation is cooperative."""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from langgraph.types import Command
from sqlalchemy import select, update

from app import obs
from app.db import get_checkpointer, get_session_factory
from app.models import Conversation, Run, RunStep
from app.orchestrator.context import (
    EVENT_BUS,
    RunContext,
    set_run_context,
)
from app.orchestrator.graph_mode import (
    RunFailed,
    build_history,
    build_orchestrator_graph,
    load_settings_snapshot,
)
from app.orchestrator.recorder import RunRecorder

logger = structlog.get_logger("orchestrator.runner")

RUNNING_TASKS: dict[UUID, asyncio.Task[None]] = {}


async def create_run(conversation_id: UUID | None, message: str, mode: str | None = None) -> Run:
    async with get_session_factory()() as session:
        if conversation_id is None:
            conversation = Conversation(title=message[:80] or "New conversation")
            session.add(conversation)
            await session.commit()
            conversation_id = conversation.id
        else:
            existing = await session.get(Conversation, conversation_id)
            if existing is None:
                raise ValueError(f"conversation {conversation_id} not found")
        settings = await load_settings_snapshot()
        run = Run(
            conversation_id=conversation_id,
            chat_message=message,
            status="running",
            orchestrator_mode=mode or str(settings["orchestrator_mode"]),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


def start_run_task(run_id: UUID, resume: dict[str, Any] | None = None) -> None:
    task = asyncio.create_task(_execute(run_id, resume=resume))
    RUNNING_TASKS[run_id] = task
    task.add_done_callback(lambda t: RUNNING_TASKS.pop(run_id, None))


async def _execute(run_id: UUID, resume: dict[str, Any] | None = None) -> None:
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        mode = run.orchestrator_mode
        task_text = run.chat_message
        conversation_id = run.conversation_id
    settings = await load_settings_snapshot()
    recorder = RunRecorder(run_id)
    ctx = RunContext(
        run_id=run_id,
        mode=mode,
        recorder=recorder,
        settings=settings,
        callbacks=obs.build_langsmith_callbacks(settings, str(run_id)),
        query_text=task_text,
    )
    set_run_context(ctx)
    if resume is None:
        obs.RUNS_TOTAL.labels(mode=mode, status="started").inc()
        recorder.emit("run_status", {"status": "running"})
    else:
        await _set_status(run_id, "running")
        recorder.emit("run_status", {"status": "running"})
    started = datetime.now(UTC)
    try:
        if mode == "agentic":
            outcome = await _run_agentic(ctx, task_text, conversation_id, resume)
        else:
            outcome = await _run_graph(ctx, task_text, conversation_id, resume)
        if outcome["paused"]:
            await _set_status(run_id, "paused_hitl")
            recorder.emit("run_status", {"status": "paused_hitl"})
            return
        answer = str(outcome.get("answer") or "")
        tool_charts = await _collect_tool_charts(run_id)
        answer_ui = await _maybe_format_answer(ctx, task_text, answer, tool_charts)
        async with get_session_factory()() as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = "completed"
                run.final_answer = answer
                run.answer_ui = answer_ui
                run.charts = tool_charts or None
                run.finished_at = datetime.now(UTC)
                await session.commit()
                totals = {
                    "input_tokens": run.total_input_tokens,
                    "output_tokens": run.total_output_tokens,
                }
        if tool_charts:
            recorder.emit("charts", {"charts": tool_charts})
        if answer_ui:
            recorder.emit("answer_ui", answer_ui)
        recorder.emit("run_status", {"status": "completed"})
        recorder.emit("done", {"answer": answer, "tokens": totals})
        obs.RUNS_TOTAL.labels(mode=mode, status="completed").inc()
        obs.RUN_DURATION.labels(mode=mode, status="completed").observe(
            (datetime.now(UTC) - started).total_seconds()
        )
    except asyncio.CancelledError:
        await _finalize_failure(run_id, mode, "cancelled", "run cancelled")
        raise
    except RunFailed as exc:
        await _finalize_failure(run_id, mode, "failed", str(exc))
    except Exception as exc:  # noqa: BLE001 - all failures surface in chat
        logger.exception("run_failed", run_id=str(run_id))
        await _finalize_failure(run_id, mode, "failed", f"{type(exc).__name__}: {exc}")


async def _collect_tool_charts(run_id: UUID) -> list[dict[str, Any]]:
    """Chart specs produced by the render_chart native tool during the run
    (spec §7.1): formatter-independent — they render with the primary answer
    in every formatter state."""
    import json

    charts: list[dict[str, Any]] = []
    async with get_session_factory()() as session:
        steps = (
            await session.execute(
                select(RunStep)
                .where(
                    RunStep.run_id == run_id,
                    RunStep.step_type == "tool_call",
                    RunStep.status == "completed",
                )
                .order_by(RunStep.started_at)
            )
        ).scalars()
        for step in steps:
            if (step.node_id or "").split(".")[-1] != "render_chart":
                continue
            raw = (step.output or {}).get("result")
            if not raw:
                continue
            try:
                spec = json.loads(str(raw))
                if isinstance(spec, dict) and spec.get("kind") and spec.get("labels"):
                    charts.append(spec)
            except (ValueError, TypeError):
                continue  # truncated/invalid output — never break the answer
    return charts


async def _maybe_format_answer(
    ctx: RunContext, task: str, answer: str, tool_charts: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The formatter role (spec §7.1): off = no call, no artifact — the raw
    answer renders directly. Fail-open: any failure returns None."""
    if not answer or not ctx.settings.get("formatter_enabled", True):
        return None
    from app.llm import ModelParams
    from app.orchestrator.answer_ui import generate_answer_ui

    ref = str(ctx.settings.get("formatter_model") or ctx.settings.get("default_model"))
    raw_params = ctx.settings.get("formatter_model_params")
    params = ModelParams.model_validate(raw_params) if raw_params else None
    presentation = str(ctx.settings.get("formatter_presentation") or "a2ui_first")
    payload, usage = await generate_answer_ui(
        ref,
        task,
        answer,
        ctx.callbacks,
        model_params=params,
        presentation=presentation,
        tool_charts=tool_charts,
    )
    if usage["input_tokens"] or usage["output_tokens"]:
        async with get_session_factory()() as session:
            run = await session.get(Run, ctx.run_id)
            if run is not None:
                run.total_input_tokens += usage["input_tokens"]
                run.total_output_tokens += usage["output_tokens"]
                await session.commit()
    return payload


async def _finalize_failure(run_id: UUID, mode: str, status: str, message: str) -> None:
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is not None:
            run.status = status
            run.error = message
            run.finished_at = datetime.now(UTC)
            await session.commit()
        await session.execute(
            update(RunStep)
            .where(RunStep.run_id == run_id, RunStep.status == "running")
            .values(status="cancelled", finished_at=datetime.now(UTC))
        )
        await session.commit()
    recorder = RunRecorder(run_id)
    if status == "failed":
        recorder.emit("error", {"message": message})
    recorder.emit("run_status", {"status": status})
    obs.RUNS_TOTAL.labels(mode=mode, status=status).inc()


async def _set_status(run_id: UUID, status: str) -> None:
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is not None:
            run.status = status
            await session.commit()


async def _run_graph(
    ctx: RunContext,
    task_text: str,
    conversation_id: UUID,
    resume: dict[str, Any] | None,
) -> dict[str, Any]:
    checkpointer = await get_checkpointer()
    graph = build_orchestrator_graph(checkpointer)
    config: dict[str, Any] = {
        "configurable": {"thread_id": str(ctx.run_id)},
        "callbacks": ctx.callbacks,
        "recursion_limit": 100,
    }
    if resume is not None:
        graph_input: Any = await _resume_command(graph, config, resume)
    else:
        history = await build_history(conversation_id)
        graph_input = {"task": task_text, "history": history}
    from typing import cast

    from langchain_core.runnables import RunnableConfig

    state = await graph.ainvoke(graph_input, config=cast(RunnableConfig, config))
    if state.get("__interrupt__"):
        if resume is not None:
            await _emit_pending_hitl(graph, config, ctx)
        return {"paused": True}
    return {"paused": False, "answer": state.get("answer", "")}


async def _pending_interrupts(graph: Any, config: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    """All pending interrupts on the thread, and the LIVE subset — parallel
    supersteps keep stale interrupts around for gates whose worker thread has
    already recorded the gate's output (answered in an earlier resume)."""
    snapshot = await graph.aget_state(config)
    pending = [i for t in (snapshot.tasks or ()) for i in t.interrupts]
    saver = await get_checkpointer()
    live: list[Any] = []
    for intr in pending:
        value = intr.value if isinstance(intr.value, dict) else {}
        thread, node = value.get("worker_thread"), value.get("node_id")
        if thread and node:
            tup = await saver.aget_tuple({"configurable": {"thread_id": thread}})
            outputs = (
                ((tup.checkpoint or {}).get("channel_values") or {}).get("node_outputs")
                if tup
                else None
            )
            if outputs and node in outputs:
                continue  # gate already answered on the worker thread
        live.append(intr)
    return pending, live


async def _resume_command(
    graph: Any, config: dict[str, Any], resume: dict[str, Any]
) -> Command[Any]:
    """One POST /hitl decision answers ONE gate. Parallel dispatch can leave
    several interrupts pending at once — target the first LIVE one by id so
    the run pauses again for the remaining gates instead of erroring."""
    pending, live = await _pending_interrupts(graph, config)
    logger.info("hitl_resume", pending=len(pending), live=len(live))
    if len(pending) > 1:
        target = live[0] if live else pending[0]
        return Command(resume={target.id: resume})
    return Command(resume=resume)


async def _emit_pending_hitl(graph: Any, config: dict[str, Any], ctx: RunContext) -> None:
    """After a resume that pauses again, re-announce the gates still waiting
    so the UI shows the next approval card."""
    _, live = await _pending_interrupts(graph, config)
    for intr in live:
        value = intr.value if isinstance(intr.value, dict) else {}
        ctx.recorder.emit(
            "hitl_request",
            {
                "prompt": value.get("prompt"),
                "node_id": value.get("node_id"),
                "step_id": value.get("dispatch_step_id"),
            },
        )


async def _run_agentic(
    ctx: RunContext,
    task_text: str,
    conversation_id: UUID,
    resume: dict[str, Any] | None,
) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage

    from app.orchestrator.agentic_mode import (
        build_agentic_agent,
        build_history_messages,
        extract_todos,
        final_answer_from_messages,
    )

    agent = await build_agentic_agent()
    config: dict[str, Any] = {
        "configurable": {"thread_id": str(ctx.run_id)},
        "callbacks": ctx.callbacks,
        "recursion_limit": 100,
    }
    if resume is not None:
        graph_input: Any = await _resume_command(agent, config, resume)
    else:
        history = await build_history_messages(conversation_id)
        graph_input = {"messages": [*history, HumanMessage(content=task_text)]}

    last_todos: list[dict[str, Any]] | None = None
    interrupted = False
    async for chunk in agent.astream(graph_input, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupted = True
            continue
        for delta in chunk.values():
            if not isinstance(delta, dict):
                continue
            todos = extract_todos(delta)
            if todos is not None and todos != last_todos:
                last_todos = todos
                ctx.recorder.emit("plan", {"todos": todos, "mode": "agentic"})
    if interrupted:
        if resume is not None:
            await _emit_pending_hitl(agent, config, ctx)
        return {"paused": True}
    state = await agent.aget_state(config)
    messages = state.values.get("messages", [])
    answer = final_answer_from_messages(messages)
    # record the final response as an aggregate step for label comparability
    step_id = await ctx.recorder.start_step("aggregate", tier="orchestrator")
    await ctx.recorder.finish_step(step_id, output={"answer": answer})
    ctx.recorder.emit("token", {"text": answer})
    return {"paused": False, "answer": answer}


# ── control operations ───────────────────────────────────────────


async def resume_run(
    run_id: UUID, decision: str, note: str = "", answers: dict[str, Any] | None = None
) -> None:
    """POST /runs/{id}/hitl (spec §7): resumes from checkpoint; approve
    continues, deny routes the node to END with the note in state; form-gate
    answers ride into worker state (spec §3.5)."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        if run.status != "paused_hitl":
            raise ValueError(f"run is {run.status}, not paused_hitl")
    resume: dict[str, Any] = {"decision": decision, "note": note}
    if answers:
        resume["answers"] = answers
    start_run_task(run_id, resume=resume)


async def cancel_run(run_id: UUID) -> None:
    """Cooperative cancel (spec §7.1); cancel on paused_hitl resolves it."""
    task = RUNNING_TASKS.get(run_id)
    if task is not None:
        task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(task, timeout=10)
        return
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        if run.status not in {"running", "paused_hitl"}:
            raise ValueError(f"run is {run.status}; only running/paused runs can be cancelled")
    await _finalize_failure(run_id, "graph", "cancelled", "cancelled while paused")


async def retry_run(run_id: UUID) -> Run:
    """Re-plan from the original message (spec §4)."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        if run.status != "failed":
            raise ValueError("only failed runs can be retried")
        conversation_id = run.conversation_id
        message = run.chat_message
    new_run = await create_run(conversation_id, message)
    start_run_task(new_run.id)
    return new_run


async def pending_hitl_runs() -> list[Run]:
    async with get_session_factory()() as session:
        return list(
            (await session.execute(select(Run).where(Run.status == "paused_hitl"))).scalars()
        )


def forget_run_events(run_id: UUID) -> None:
    EVENT_BUS.forget(run_id)
