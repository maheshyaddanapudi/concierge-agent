"""Middleware layer (spec §7.0) — the sync backbone for every create_agent loop.

The three registry middlewares are the ONLY path by which capabilities reach
any create_agent instance. They are stateless projections over Postgres:
fresh reads per model call, no shared state — reuse is by class + config.

Composition happens through build_middleware_stack(context), used everywhere:
- SkillLoopContext → SummarizationMiddleware + call limits + ToolsRegistry in
  scoped mode (the skill's bound tool ids only; never Skills/SubAgents
  registry middleware — §3.3 isolation is enforced structurally).
- Orchestrator contexts (M4) → all three registry middlewares + TodoList +
  Summarization + limits.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

logger = structlog.get_logger("orchestrator.middleware")


class ToolExecutionFailed(RuntimeError):
    """A tool call inside a skill loop failed — node-level error semantics
    (spec §3.5: tool/MCP error routes the node's error edge)."""


@dataclass
class SkillLoopContext:
    """Scoped stack for any skill loop: DAG nodes, rung-1 inline execution,
    ephemeral workers, and skills invoked from fallback (spec §7.0)."""

    skill_id: str | None
    bound_tool_ids: list[str]
    model: BaseChatModel
    max_tool_iterations: int
    # tool/MCP errors abort the node (spec §3.5); orchestrator loops relax this
    strict_tool_errors: bool = True


class ToolsRegistryMiddleware(AgentMiddleware[Any, Any]):
    """Dynamic-tools hook: resolves live tool objects from the tool registry
    at each model call (spec §7.0). Scoped mode resolves the bound ids only —
    a reconnected MCP server or re-ingested tool is visible on the next loop
    iteration with no rebuild.
    """

    def __init__(
        self,
        *,
        scoped_tool_ids: list[str] | None = None,
        full_catalog: bool = False,
        strict_tool_errors: bool = False,
    ) -> None:
        super().__init__()
        self._scoped_tool_ids = scoped_tool_ids
        self._full_catalog = full_catalog
        self._strict_tool_errors = strict_tool_errors
        self._current: dict[str, BaseTool] = {}

    async def _resolve(self) -> list[BaseTool]:
        from app.factory.worker import resolve_tools_by_ids

        ids = [UUID(t) for t in self._scoped_tool_ids or []]
        tools = await resolve_tools_by_ids(ids)
        self._current = {t.name: t for t in tools}
        return tools

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        tools = await self._resolve()
        return await handler(request.override(tools=tools))

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = request.tool_call["name"]
        tool = self._current.get(name)
        result = await handler(request.override(tool=tool) if tool is not None else request)
        if (
            self._strict_tool_errors
            and isinstance(result, ToolMessage)
            and result.status == "error"
        ):
            raise ToolExecutionFailed(f"tool {name!r} failed: {result.content}")
        return result


@dataclass
class _StackParts:
    middlewares: list[AgentMiddleware[Any, Any]] = field(default_factory=list)


def build_middleware_stack(context: SkillLoopContext) -> list[AgentMiddleware[Any, Any]]:
    """One helper, used everywhere (spec §7.0). M4 extends the accepted
    contexts with the graph-fallback and agentic-orchestrator stacks."""
    if isinstance(context, SkillLoopContext):
        return [
            SummarizationMiddleware(model=context.model),
            # +1: an N-iteration tool loop is N tool rounds plus the final
            # answer call; exceeding it must fail the node (spec §3.7)
            ModelCallLimitMiddleware(
                run_limit=context.max_tool_iterations + 1, exit_behavior="error"
            ),
            ToolsRegistryMiddleware(
                scoped_tool_ids=context.bound_tool_ids,
                strict_tool_errors=context.strict_tool_errors,
            ),
        ]
    raise TypeError(f"unknown middleware context: {type(context).__name__}")
