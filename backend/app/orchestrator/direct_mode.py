"""Direct sub-agent invocation (spec §7.5): the user pins the sub agent, so
the pin replaces the ROUTING decision — never the run lifecycle. A one-node
graph on the run's checkpointer thread reuses the ladder executor, so HITL
pause/resume, step recording, and worker code paths are identical to routed
dispatch; the runner's shared tail applies the formatter and finalization
exactly as for graph/agentic runs."""

from typing import Any, TypedDict

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.orchestrator.context import require_run_context

logger = structlog.get_logger("orchestrator.direct")

# the single dispatch slot on a direct run — worker thread ids and step
# node_ids both key off it, mirroring graph-mode plan-entry ids
DIRECT_ENTRY_ID = "direct"


class DirectState(TypedDict, total=False):
    task: str
    sub_agent_id: str
    answer: str


class DirectInvokeError(RuntimeError):
    """The pinned sub agent cannot be invoked (gating or execution failure)."""


async def check_direct_invokable(sub_agent_id: str) -> dict[str, Any]:
    """Gating (spec §7.5): active + direct_exposure, from the registry cache.
    Returns the cached record; raises DirectInvokeError with the reason."""
    from app.registry_cache import get_cache

    record = await get_cache().sub_agent_by_id(sub_agent_id)
    if record is None:
        raise DirectInvokeError(f"sub agent {sub_agent_id} not found")
    if record["status"] != "active":
        raise DirectInvokeError(f"sub agent {record['name']!r} is not active")
    if not record["direct_exposure"]:
        raise DirectInvokeError(
            f"sub agent {record['name']!r} is not exposed for direct invocation"
        )
    return record


async def invoke_node(state: DirectState) -> dict[str, Any]:
    """Resolve the pinned agent through the ladder's sub-agent rungs and run
    it with HITL propagation — the exact executor routed dispatch uses."""
    from app.orchestrator.graph_mode import RunFailed
    from app.orchestrator.ladder import execute_resolution, resolve_capability

    # defense in depth: re-check the gate at execution start — a toggle
    # flipped between request and execution fails the run cleanly
    try:
        await check_direct_invokable(state["sub_agent_id"])
    except DirectInvokeError as exc:
        raise RunFailed(str(exc)) from exc

    resolution = await resolve_capability({"type": "sub_agent", "id": state["sub_agent_id"]})
    result = await execute_resolution(resolution, state["task"], DIRECT_ENTRY_ID)
    if result.get("status") == "error":
        raise RunFailed(
            f"direct invocation of {resolution.entity_name!r} failed: {result.get('error')}"
        )
    return {"answer": str(result.get("output") or "")}


def build_direct_graph(
    checkpointer: BaseCheckpointSaver[Any] | None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph: StateGraph[DirectState, Any, Any, Any] = StateGraph(DirectState)
    graph.add_node("invoke", invoke_node)
    graph.add_edge(START, "invoke")
    graph.add_edge("invoke", END)
    return graph.compile(checkpointer=checkpointer)


async def record_direct_route(sub_agent_id: str) -> None:
    """One route step per direct run (spec §7.5) — recorded before the graph
    starts so HITL resume replays never duplicate it. Trace parity: the same
    rung names routed dispatch would log."""
    from app.orchestrator.ladder import resolve_capability

    ctx = require_run_context()
    resolution = await resolve_capability({"type": "sub_agent", "id": sub_agent_id})
    await ctx.recorder.record_route(
        capability={"type": "sub_agent", "id": sub_agent_id, "pinned": True},
        rung=resolution.rung,
        resolved_to={"entity_id": resolution.entity_id, "entity_name": resolution.entity_name},
        kind=resolution.kind,
        source=resolution.source,
    )
