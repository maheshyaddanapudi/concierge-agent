"""Capability resolution ladder + execution (spec §7.1).

Rungs, in order: direct (exposed tool / exposed skill) → native sub agent via
covers_skill_ids → custom sub agent via sub_agent_skills → ephemeral dynamic
worker. Deterministic; every resolution is logged as a `route` step. The same
executor backs graph-mode dispatch and the agentic middlewares' handlers.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage
from langgraph.types import Command, interrupt
from sqlalchemy import select

from app.db import get_checkpointer, get_session_factory
from app.factory.worker import (
    build_ephemeral_snapshot,
    get_compiled_worker,
    get_native_worker,
    resolve_tools_by_ids,
    snapshot_skill,
    snapshot_sub_agent,
)
from app.llm import get_model, text_from_content
from app.models import Skill, SubAgent, Tool, sub_agent_skills
from app.orchestrator.context import require_run_context
from app.prompts import load_prompt

logger = structlog.get_logger("orchestrator.ladder")


class ResolutionError(RuntimeError):
    """No rung can service the capability."""


@dataclass
class Resolution:
    rung: str  # direct_tool | direct_skill | native_sub_agent | custom_sub_agent | dynamic_worker
    tier: str
    kind: str
    source: str
    entity_id: str | None
    entity_name: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_route(self) -> dict[str, Any]:
        return {
            "rung": self.rung,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "tier": self.tier,
            "kind": self.kind,
        }


async def resolve_capability(capability: dict[str, Any]) -> Resolution:
    """Deterministic ladder (spec §7.1). `capability` is a plan-entry
    capability dict: {type, id?, skill_ids?}."""
    ctx_type = capability.get("type")
    async with get_session_factory()() as session:
        if ctx_type == "direct_tool":
            tool = await session.get(Tool, UUID(str(capability["id"])))
            if tool is None or tool.deleted_at is not None or tool.status != "active":
                raise ResolutionError(f"tool {capability.get('id')} is not active")
            if not tool.direct_exposure:
                raise ResolutionError(f"tool {tool.tool_key!r} is not exposed to the orchestrator")
            return Resolution(
                rung="direct_tool",
                tier="tool",
                kind=tool.kind,
                source=tool.source,
                entity_id=str(tool.id),
                entity_name=tool.tool_key,
                payload={"tool_id": str(tool.id)},
            )

        if ctx_type == "direct_skill":
            skill = await session.get(Skill, UUID(str(capability["id"])))
            if skill is None or skill.deleted_at is not None or skill.status != "active":
                raise ResolutionError(f"skill {capability.get('id')} is not active")
            if skill.direct_exposure:
                snap = await snapshot_skill(session, skill)
                return Resolution(
                    rung="direct_skill",
                    tier="skill",
                    kind=skill.kind,
                    source=skill.source,
                    entity_id=str(skill.id),
                    entity_name=skill.name,
                    payload={"skill": snap},
                )
            # rung 2: native sub agent whose covers_skill_ids includes the skill
            natives = (
                (
                    await session.execute(
                        select(SubAgent).where(
                            SubAgent.deleted_at.is_(None),
                            SubAgent.status == "active",
                            SubAgent.kind == "native",
                        )
                    )
                )
                .scalars()
                .all()
            )
            for agent in natives:
                if str(skill.id) in [str(x) for x in (agent.covers_skill_ids or [])]:
                    return Resolution(
                        rung="native_sub_agent",
                        tier="sub_agent",
                        kind="native",
                        source=agent.source,
                        entity_id=str(agent.id),
                        entity_name=agent.name,
                        payload={"native_name": agent.name},
                    )
            # rung 3: custom sub agent whose workflow includes the skill
            custom_row = (
                (
                    await session.execute(
                        select(SubAgent)
                        .join(sub_agent_skills, sub_agent_skills.c.sub_agent_id == SubAgent.id)
                        .where(
                            sub_agent_skills.c.skill_id == skill.id,
                            SubAgent.deleted_at.is_(None),
                            SubAgent.status == "active",
                            SubAgent.kind == "custom",
                        )
                        .order_by(SubAgent.created_at)
                    )
                )
                .scalars()
                .first()
            )
            if custom_row is not None:
                snap = await snapshot_sub_agent(session, custom_row)
                return Resolution(
                    rung="custom_sub_agent",
                    tier="sub_agent",
                    kind="custom",
                    source=custom_row.source,
                    entity_id=str(custom_row.id),
                    entity_name=custom_row.name,
                    payload={"snapshot": snap},
                )
            # rung 4: ephemeral dynamic worker
            return await _dynamic_resolution(session, [str(skill.id)])

        if ctx_type == "sub_agent":
            found = await session.get(SubAgent, UUID(str(capability["id"])))
            if found is None or found.deleted_at is not None or found.status != "active":
                raise ResolutionError(f"sub agent {capability.get('id')} is not active")
            agent_row = found
            if agent_row.kind == "native":
                return Resolution(
                    rung="native_sub_agent",
                    tier="sub_agent",
                    kind="native",
                    source=agent_row.source,
                    entity_id=str(agent_row.id),
                    entity_name=agent_row.name,
                    payload={"native_name": agent_row.name},
                )
            snap = await snapshot_sub_agent(session, agent_row)
            return Resolution(
                rung="custom_sub_agent",
                tier="sub_agent",
                kind="custom",
                source=agent_row.source,
                entity_id=str(agent_row.id),
                entity_name=agent_row.name,
                payload={"snapshot": snap},
            )

        if ctx_type == "spin_worker":
            return await _dynamic_resolution(
                session, [str(s) for s in capability.get("skill_ids") or []]
            )

    raise ResolutionError(f"unknown capability type {ctx_type!r}")


async def _dynamic_resolution(session: Any, skill_ids: list[str]) -> Resolution:
    from app.settings_store import get_setting

    if not await get_setting(session, "dynamic_worker_fallback_enabled"):
        raise ResolutionError("dynamic worker fallback is disabled")
    snaps: list[dict[str, Any]] = []
    for sid in skill_ids:
        skill = await session.get(Skill, UUID(sid))
        if skill is None or skill.deleted_at is not None or skill.status != "active":
            raise ResolutionError(f"skill {sid} is not active")
        snaps.append(await snapshot_skill(session, skill))
    if not snaps:
        raise ResolutionError("spin_worker needs at least one skill")
    return Resolution(
        rung="dynamic_worker",
        tier="sub_agent",
        kind="dynamic",
        source="dynamic",
        entity_id=None,
        entity_name="ephemeral-worker",
        payload={"skills": snaps},
    )


# ── execution ────────────────────────────────────────────────────


async def run_inline_skill(
    skill_snapshot: dict[str, Any],
    task: str,
    *,
    parent_step_id: UUID | None = None,
    record: bool = True,
) -> dict[str, Any]:
    """Rung-1 inline skill loop: create_agent with the scoped skill stack —
    persona + instructions + bound tools, nothing else (spec §7.1, §3.3)."""
    from langchain.agents import create_agent

    from app.factory.worker import (
        _usage_from_messages,
        assemble_skill_prompt,
        resolve_node_model,
    )
    from app.orchestrator.middleware import SkillLoopContext, build_middleware_stack
    from app.settings_store import get_setting

    ctx = require_run_context()
    step_id: UUID | None = None
    if record:
        step_id = await ctx.recorder.start_step(
            "skill",
            tier="skill",
            kind="custom" if skill_snapshot.get("id") else "dynamic",
            source="dynamic",
            entity_id=skill_snapshot.get("id"),
            entity_name=skill_snapshot.get("name"),
            parent_step_id=parent_step_id,
            input={"task": task},
            emit_dispatch=True,
        )
    try:
        model_ref, params = await resolve_node_model(skill_snapshot, {})
        model = get_model(model_ref, params)
        async with get_session_factory()() as session:
            max_iter = int(await get_setting(session, "max_tool_iterations"))
        stack = build_middleware_stack(
            SkillLoopContext(
                skill_id=skill_snapshot.get("id"),
                bound_tool_ids=[t["id"] for t in skill_snapshot.get("tools", [])],
                model=model,
                max_tool_iterations=max_iter,
            )
        )
        prompt = assemble_skill_prompt(
            "", skill_snapshot.get("persona", ""), skill_snapshot.get("instructions", "")
        )
        agent = create_agent(model, tools=[], system_prompt=prompt, middleware=stack)
        from app.orchestrator.middleware import current_step

        with current_step(step_id):
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={"callbacks": ctx.callbacks},
            )
        messages = result["messages"]
        text = text_from_content(messages[-1].content)
        usage = _usage_from_messages(messages)
        output = {"status": "ok", "output": text if isinstance(text, str) else str(text)}
        if step_id is not None:
            await ctx.recorder.finish_step(
                step_id,
                output=output,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                emit_dispatch=True,
            )
        return output
    except Exception as exc:  # noqa: BLE001
        if step_id is not None:
            await ctx.recorder.finish_step(
                step_id, status="failed", error=str(exc), emit_dispatch=True
            )
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


async def run_direct_tool(
    tool_id: str, task: str, *, parent_step_id: UUID | None = None
) -> dict[str, Any]:
    """Rung-1 direct tool: a plain tool call under the orchestrator's own
    prompt — one model call to derive arguments, then execute (spec §7.1)."""
    ctx = require_run_context()
    tools = await resolve_tools_by_ids([UUID(tool_id)])
    if not tools:
        return {"status": "error", "error": f"tool {tool_id} is not active"}
    tool = tools[0]
    step_id = await ctx.recorder.start_step(
        "tool_call",
        tier="tool",
        kind="mcp",
        source="dynamic",
        entity_id=tool_id,
        entity_name=tool.name,
        parent_step_id=parent_step_id,
        input={"task": task},
        emit_dispatch=True,
    )
    try:
        from app.factory.worker import resolve_node_model

        model_ref, params = await resolve_node_model({}, {})
        model = get_model(model_ref, params).bind_tools([tool])
        prompt = load_prompt("direct_tool").format(task=task)
        ai = await model.ainvoke(prompt, config={"callbacks": ctx.callbacks})
        usage = getattr(ai, "usage_metadata", None) or {}
        if not getattr(ai, "tool_calls", None):
            text = text_from_content(ai.content)
            output = {"status": "ok", "output": text}
        else:
            call = ai.tool_calls[0]
            result = await tool.ainvoke(call["args"])
            output = {"status": "ok", "output": text_from_content(result)}
        await ctx.recorder.finish_step(
            step_id,
            output=output,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            emit_dispatch=True,
        )
        return output
    except Exception as exc:  # noqa: BLE001
        await ctx.recorder.finish_step(step_id, status="failed", error=str(exc), emit_dispatch=True)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


async def invoke_worker_with_hitl(
    worker: Any,
    task: str,
    thread_id: str,
    *,
    sub_agent_id: str | None,
    sub_agent_name: str,
    kind: str,
    source: str,
    parent_step_id: UUID | None = None,
) -> dict[str, Any]:
    """Invoke a compiled worker, recording its node outputs as run steps and
    propagating interrupt() to the caller for HITL (idempotent on replay —
    resume replays this handler, which picks up the paused thread instead of
    restarting it, spec §7.0)."""
    ctx = require_run_context()
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "callbacks": ctx.callbacks,
    }
    recorded: set[str] = set()

    async def record_new_outputs(state_values: dict[str, Any]) -> None:
        outputs = state_values.get("node_outputs", {}) if state_values else {}
        for node_id in sorted(outputs):
            if node_id in recorded:
                continue
            recorded.add(node_id)
            out = outputs[node_id]
            if node_id.startswith("route:"):
                step_type = "route"
                status = "completed"
            elif isinstance(out, dict) and out.get("node_type") == "hitl":
                step_type = "hitl"
                status = "completed"
            elif isinstance(out, dict) and out.get("status") == "error":
                step_type = "skill"
                status = "failed"
            else:
                step_type = "skill"
                status = "completed"
            usage = out.get("usage", {}) if isinstance(out, dict) else {}
            step_id = await ctx.recorder.start_step(
                step_type,
                tier="sub_agent" if step_type != "route" else "orchestrator",
                kind=kind,
                source=source,
                entity_id=out.get("skill_id") if isinstance(out, dict) else None,
                entity_name=out.get("skill_name") if isinstance(out, dict) else None,
                node_id=node_id,
                sub_agent_id=sub_agent_id,
                parent_step_id=parent_step_id,
                model=out.get("model") if isinstance(out, dict) else None,
                effort=out.get("effort") if isinstance(out, dict) else None,
            )
            await ctx.recorder.finish_step(
                step_id,
                status=status,
                output=out if isinstance(out, dict) else {"output": str(out)},
                error=out.get("error") if isinstance(out, dict) else None,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

    # idempotent replay: a paused thread resumes; a fresh one starts
    snapshot = await worker.aget_state(config)
    pending_interrupt = None
    suppress_emit = False
    if snapshot is not None and snapshot.next:
        for t in snapshot.tasks:
            if t.interrupts:
                pending_interrupt = t.interrupts[0].value
        outputs = (snapshot.values or {}).get("node_outputs", {})
        recorded.update(outputs.keys())
        if pending_interrupt is not None:
            # replay: each hitl node completed before this pause consumed one
            # resume value — burn that many interrupt() calls so the pending
            # one lines up with the resume value being delivered now, and
            # don't re-emit the hitl_request that was emitted before pausing
            prior_hitl = sum(
                1 for v in outputs.values() if isinstance(v, dict) and v.get("node_type") == "hitl"
            )
            for _ in range(prior_hitl):
                interrupt(pending_interrupt)
            suppress_emit = True
        graph_input: Any = None
    else:
        graph_input = {"task": task, "messages": []}

    while True:
        if pending_interrupt is not None:
            if not suppress_emit:
                ctx.recorder.emit(
                    "hitl_request",
                    {
                        "prompt": pending_interrupt.get("prompt"),
                        "node_id": pending_interrupt.get("node_id"),
                    },
                )
            suppress_emit = False
            decision = interrupt(pending_interrupt)
            graph_input = Command(resume=decision)
            pending_interrupt = None
        state = await worker.ainvoke(graph_input, config=config)
        await record_new_outputs(state)
        interrupts = state.get("__interrupt__") if isinstance(state, dict) else None
        if interrupts:
            pending_interrupt = interrupts[0].value
            continue
        outputs = state.get("node_outputs", {})
        parts = [
            str(outputs[k].get("output", ""))
            for k in sorted(outputs)
            if not k.startswith("route:") and outputs[k].get("status") == "ok"
        ]
        return {"status": "ok", "output": "\n".join(p for p in parts if p) or "(no output)"}


async def find_running_dispatch(run_id: UUID, node_id: str) -> UUID | None:
    """A dispatch step left `running` marks a HITL pause — its presence tells
    a replayed handler to adopt it instead of recording a duplicate."""
    from app.models import RunStep

    async with get_session_factory()() as session:
        row = (
            (
                await session.execute(
                    select(RunStep).where(
                        RunStep.run_id == run_id,
                        RunStep.node_id == node_id,
                        RunStep.step_type == "skill",
                        RunStep.status == "running",
                    )
                )
            )
            .scalars()
            .first()
        )
        return row.id if row is not None else None


async def execute_resolution(resolution: Resolution, task: str, entry_id: str) -> dict[str, Any]:
    """Execute a resolved capability, recording a dispatch step (spec §7.1)."""
    ctx = require_run_context()
    if resolution.rung == "direct_tool":
        return await run_direct_tool(str(resolution.payload["tool_id"]), task)
    if resolution.rung == "direct_skill":
        return await run_inline_skill(resolution.payload["skill"], task)

    step_id = await find_running_dispatch(ctx.run_id, entry_id)
    if step_id is None:
        step_id = await ctx.recorder.start_step(
            "skill",
            tier="sub_agent",
            kind=resolution.kind,
            source=resolution.source,
            entity_id=resolution.entity_id,
            entity_name=resolution.entity_name,
            sub_agent_id=resolution.entity_id,
            node_id=entry_id,
            input={"task": task},
            emit_dispatch=True,
        )
    try:
        checkpointer = await get_checkpointer()
        if resolution.rung == "native_sub_agent":
            worker = get_native_worker(resolution.payload["native_name"], checkpointer)
        elif resolution.rung == "custom_sub_agent":
            worker = get_compiled_worker(resolution.payload["snapshot"], checkpointer)
        else:  # dynamic_worker
            snapshot = build_ephemeral_snapshot(resolution.payload["skills"], task)
            worker = get_compiled_worker(snapshot, checkpointer)
        from app.orchestrator.middleware import current_step

        with current_step(step_id):
            result = await invoke_worker_with_hitl(
                worker,
                task,
                thread_id=f"{ctx.run_id}:{entry_id}",
                sub_agent_id=resolution.entity_id,
                sub_agent_name=resolution.entity_name,
                kind=resolution.kind,
                source=resolution.source,
                parent_step_id=step_id,
            )
        await ctx.recorder.finish_step(step_id, output=result, emit_dispatch=True)
        return result
    except Exception as exc:
        # interrupts propagate as GraphInterrupt subclasses — let them through
        from langgraph.errors import GraphInterrupt

        if isinstance(exc, GraphInterrupt):
            raise
        await ctx.recorder.finish_step(step_id, status="failed", error=str(exc), emit_dispatch=True)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
