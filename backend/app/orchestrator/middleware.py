"""Middleware layer (spec §7.0) — the sync backbone for every create_agent loop.

The three registry middlewares are the ONLY path by which capabilities reach
any create_agent instance. They are stateless projections over Postgres:
fresh reads per model call, no shared state — reuse is by class + config.

Composition happens through build_middleware_stack(context), used everywhere:
- SkillLoopContext → Summarization + call limits + ToolsRegistry in scoped
  mode (bound tool ids only; never Skills/SubAgents middleware — §3.3
  isolation is enforced structurally).
- FallbackLoopContext → Summarization + limits + ToolsRegistry + SkillsRegistry
  in full-catalog mode (exposure flags ignored; skill handlers stay isolated).
- AgenticLoopContext → TodoList + Summarization + limits + all three registry
  middlewares, exposure-gated; the use_full_catalog escalation flips them to
  full-catalog mid-loop via the run flags.
"""

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import structlog
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
    TodoListMiddleware,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from app import obs
from app.orchestrator.context import get_run_context

logger = structlog.get_logger("orchestrator.middleware")

# parent step for nested tool_call recording (set by skill/dispatch executors)
CURRENT_STEP_ID: ContextVar[UUID | None] = ContextVar("current_step_id", default=None)
# holder mutated by native tool wrappers to report nested LLM usage (spec §5b)
TOOL_USAGE_HOLDER: ContextVar[dict[str, int] | None] = ContextVar("tool_usage_holder", default=None)


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
    strict_tool_errors: bool = True


@dataclass
class FallbackLoopContext:
    """Self-service full-catalog fallback (spec §7.0)."""

    model: BaseChatModel
    max_tool_iterations: int


@dataclass
class AgenticLoopContext:
    """Agentic orchestrator (spec §7.2): exposure-gated registry middlewares."""

    model: BaseChatModel
    max_tool_iterations: int


ToolsMode = Literal["scoped", "exposed", "full_catalog"]
# tools a loop carries that are not registry tools — never "unavailable"
KNOWN_LOOP_TOOLS = {"spin_worker", "use_full_catalog", "write_todos"}
# the names the sibling registry projections attach per model call
# (skills, sub agent dispatch): theirs to resolve, not the tools registry's
SIBLING_TOOL_PREFIXES = ("use_skill_", "dispatch_")


def log_catalog_call(kind: str, mode: str, shown: list[str]) -> None:
    """Spec §3.6: what this model call could see — the shown ids per call
    and registry, bounded, onto the run's snapshot at the end. Without it
    a catalog frozen at start says nothing about which records ranking or
    an allowlist left out of a given call. A call shown the same slice as
    the previous one of its kind is not repeated."""
    ctx = get_run_context()
    if ctx is None:
        return
    last = next((c for c in reversed(ctx.catalog_calls) if c.get("kind") == kind), None)
    if last is not None and last.get("shown") == shown and last.get("mode") == mode:
        last["repeats"] = int(last.get("repeats") or 1) + 1
        return
    entry = {
        "step_id": str(CURRENT_STEP_ID.get()) if CURRENT_STEP_ID.get() else None,
        "kind": kind,
        "mode": mode,
        "shown": shown,
    }
    if len(ctx.catalog_calls) < 200:
        ctx.catalog_calls.append(entry)


async def _record_tool_call(
    name: str,
    kind: str | None,
    source: str | None,
    entity_id: str | None,
    *,
    schema_version: int | None = None,
    schema_hash: str | None = None,
) -> UUID | None:
    ctx = get_run_context()
    if ctx is None:
        return None
    step_id: UUID = await ctx.recorder.start_step(
        "tool_call",
        tier="tool",
        kind=kind,
        source=source,
        entity_id=entity_id,
        entity_name=name,
        # persist the tool name on the step (node_id): traces show it and
        # the runner's render_chart collection depends on it (spec §7.1)
        node_id=name,
        parent_step_id=CURRENT_STEP_ID.get(),
        # spec §3.2 drift: the schema version the call was made against
        entity_version=schema_version,
        entity_hash=schema_hash,
    )
    return step_id


async def _finish_tool_call(
    step_id: UUID | None,
    *,
    status: str,
    output: str | None,
    error: str | None,
    usage: dict[str, int],
    kind: str | None,
    source: str | None,
) -> None:
    ctx = get_run_context()
    if ctx is None or step_id is None:
        return
    obs.TOOL_CALLS_TOTAL.labels(kind=kind or "-", source=source or "-", status=status).inc()
    await ctx.recorder.finish_step(
        step_id,
        status=status,
        output={"result": (output or "")[:4000]} if output else None,
        error=error,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )


class ToolsRegistryMiddleware(AgentMiddleware[Any, Any]):
    """Dynamic-tools hook (spec §7.0): resolves live tool objects from the
    tool registry at each model call. Scoped mode = a skill's bound ids only;
    exposed mode = direct_exposure tools; full-catalog = every active tool.
    In exposed mode the run's full_catalog flag escalates live."""

    def __init__(
        self,
        *,
        mode: ToolsMode,
        scoped_tool_ids: list[str] | None = None,
        strict_tool_errors: bool = False,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._scoped_tool_ids = scoped_tool_ids or []
        self._strict_tool_errors = strict_tool_errors
        self._current: dict[str, BaseTool] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._reported_missing: set[str] = set()
        # sanitized name → reason, for bound tools that did not resolve
        self._missing_names: dict[str, str] = {}
        self._last_shown: list[str] = []

    def _effective_mode(self) -> ToolsMode:
        ctx = get_run_context()
        if self._mode == "exposed" and ctx is not None and ctx.flags.full_catalog:
            return "full_catalog"
        return self._mode

    async def _resolve(self) -> list[BaseTool]:
        from app.factory.worker import materialize_tool
        from app.registry_cache import get_cache
        from app.retrieval import apply_ambient_allowlist, apply_retrieval

        mode = self._effective_mode()
        cache = get_cache()
        if mode == "scoped":
            records = await cache.tools_by_ids([UUID(t) for t in self._scoped_tool_ids])
        else:
            records = await cache.tools(exposed_only=mode == "exposed")
            # §17.4: the ambient allowlist narrows even the full-catalog
            # escape hatch — scoped loops stay pinned contracts
            records = apply_ambient_allowlist(records, kind="tools")
            if mode == "exposed":
                # progressive disclosure (spec §7.4) applies to the orchestrator
                # catalog only — scoped loops are pinned contracts, full-catalog
                # is the deliberate escape hatch past ranking
                records, _dropped = await apply_retrieval(records, kind="tools")
        if mode == "scoped":
            # spec §3.3 "binding = availability, strictly": a bound tool that
            # did not resolve (inactive, quarantined, deleted, dropped by its
            # server) is a tool the instructions still name — say so, count
            # it, and put it on the trace instead of letting the loop run
            # half-blind and silent
            resolved_ids = {str(r["id"]) for r in records}
            missing = [t for t in self._scoped_tool_ids if str(t) not in resolved_ids]
            if missing and set(missing) != self._reported_missing:
                self._reported_missing = set(missing)
                # the reason per tool, from the row the cache still holds
                # (inactive rows stay cached; a deleted one is gone)
                from app.factory.worker import sanitize_tool_name

                reasons: dict[str, str] = {}
                self._missing_names = {}
                for tool_id in missing:
                    row = await cache.tool_by_id(tool_id)
                    if row is None:
                        reason = "deleted"
                    elif row.get("ingest_state") == "changed":
                        reason = "quarantined"
                    elif row.get("ingest_state") == "missing":
                        reason = "missing"
                    else:
                        reason = str(row.get("status") or "inactive")
                    reasons[str(tool_id)] = reason
                    if row is not None:
                        self._missing_names[sanitize_tool_name(row["tool_key"])] = reason
                    obs.SKILL_TOOL_UNAVAILABLE.labels(reason=reason).inc()
                logger.warning(
                    "skill_bound_tool_unavailable",
                    tier="skill",
                    kind="bind",
                    missing_tool_ids=missing,
                    reasons=reasons,
                    resolved=len(records),
                )
                ctx = get_run_context()
                if ctx is not None:
                    ctx.recorder.emit(
                        "activity",
                        {"label": f"skill: {len(missing)} bound tool(s) unavailable at bind time"},
                    )
                    # onto the stored run, not only the live stream: a loop
                    # that never calls the missing tool still ran half-blind
                    ctx.log_context(
                        "skill_bind",
                        step_id=str(CURRENT_STEP_ID.get()) if CURRENT_STEP_ID.get() else None,
                        missing=reasons,
                        resolved=sorted(resolved_ids),
                    )
        # sanitized names can collide even though tool_keys are unique —
        # bind first-wins, because duplicate bound names are a provider
        # error; the metadata recorded on a call is the BOUND tool's, never
        # the skipped one's (the hardening wave: `_meta` used to be built
        # from every record, last-wins, so a call ran tool A and was
        # stamped with tool B's id, version and hash)
        deduped: dict[str, BaseTool] = {}
        meta: dict[str, dict[str, Any]] = {}
        for record in records:
            tool = materialize_tool(record)
            if tool is None:
                continue
            if tool.name in deduped:
                obs.TOOL_NAME_COLLISIONS.inc()
                logger.warning(
                    "tool_name_collision_skipped",
                    name=tool.name,
                    skipped_tool_key=record["tool_key"],
                    bound_tool_id=meta[tool.name]["id"],
                )
                continue
            deduped[tool.name] = tool
            meta[tool.name] = {
                "kind": record["kind"],
                "source": record["source"],
                "id": record["id"],
                "tool_key": record["tool_key"],
                "schema_version": record.get("schema_version"),
                "schema_hash": record.get("schema_hash"),
            }
        self._current = deduped
        self._meta = meta
        self._last_shown = [str(r["id"]) for r in records]
        return list(deduped.values())

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        tools = await self._resolve()
        # the slice this MODEL CALL was shown (a tool-call replay resolves
        # too, but is not a model call — review round 2)
        log_catalog_call("tools", self._effective_mode(), self._last_shown)
        return await handler(request.override(tools=[*request.tools, *tools]))

    async def _check_paused_schema(self, name: str, meta: dict[str, Any]) -> None:
        """A HITL resume replays the interrupted tool call with arguments
        the model produced against the schema of that moment; if the tool's
        schema changed while the run was paused, say so on the log — the
        step records the version it runs against now, the args are older."""
        ctx = get_run_context()
        if ctx is None or not meta.get("schema_hash"):
            return
        from sqlalchemy import select

        from app.db import get_session_factory
        from app.models import RunStep

        async with get_session_factory()() as session:
            prior = (
                await session.execute(
                    select(RunStep.entity_hash, RunStep.entity_version)
                    .where(
                        RunStep.run_id == ctx.run_id,
                        RunStep.step_type == "tool_call",
                        RunStep.node_id == name,
                        RunStep.status == "running",
                    )
                    .order_by(RunStep.started_at.desc())
                    .limit(1)
                )
            ).first()
        if prior is not None and prior[0] and prior[0] != meta.get("schema_hash"):
            logger.warning(
                "tool_schema_changed_during_pause",
                tool=name,
                paused_version=prior[1],
                current_version=meta.get("schema_version"),
                run_id=str(ctx.run_id),
            )

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = request.tool_call["name"]
        tool = self._current.get(name)
        if tool is None:
            # HITL resume replays the interrupted tool call before any model
            # call runs, so a fresh instance must resolve its registry here.
            await self._resolve()
            tool = self._current.get(name)
        if tool is None:
            if (
                request.tool is not None
                or name in KNOWN_LOOP_TOOLS
                or name.startswith(SIBLING_TOOL_PREFIXES)
            ):
                # a tool the loop itself registered with its ToolNode (the
                # agentic loop's spin_worker / use_full_catalog, a native
                # HITL gate) or one a sibling projection attaches per model
                # call (use_skill_*, dispatch_*) is not a registry tool —
                # not ours to judge. Registry tools are attached per model
                # call too, so for them `request.tool` is None and
                # `_current` is the authority
                return await handler(request)
            # the model called a tool this loop does not have — a FAILED
            # tool_call step so the trace shows it, never a silent "not a
            # valid tool" burn of the iteration budget. Two cases (review
            # round 2): a BOUND tool that went inactive, quarantined or
            # missing is the contract broken — in a strict loop that is the
            # node's error edge (spec §3.5); a name the loop never had (a
            # hallucination, an unsanitized key) is the model's own slip and
            # gets the error message back to correct itself, as before
            bound_reason = self._missing_names.get(name)
            obs.SKILL_TOOL_UNAVAILABLE.labels(
                reason=f"called:{bound_reason}" if bound_reason else "called:unknown"
            ).inc()
            error = (
                f"tool {name!r} is bound to this skill but unavailable ({bound_reason})"
                if bound_reason
                else f"tool {name!r} is not a tool of this loop; use one of "
                f"{sorted(self._current) or '(none)'}"
            )
            step_id = await _record_tool_call(name, None, None, None)
            await _finish_tool_call(
                step_id, status="failed", output=None, error=error, usage={}, kind=None, source=None
            )
            if self._strict_tool_errors and bound_reason:
                raise ToolExecutionFailed(error)
            return ToolMessage(
                content=error, name=name, tool_call_id=request.tool_call["id"], status="error"
            )
        meta = self._meta.get(name, {})
        ctx_now = get_run_context()
        if ctx_now is not None and ctx_now.resumed:
            # only a resumed run can be replaying arguments made against an
            # older schema — no query per call otherwise
            await self._check_paused_schema(name, meta)
        step_id = await _record_tool_call(
            name,
            meta.get("kind"),
            meta.get("source"),
            meta.get("id"),
            schema_version=meta.get("schema_version"),
            schema_hash=meta.get("schema_hash"),
        )
        holder: dict[str, int] = {}
        token = TOOL_USAGE_HOLDER.set(holder)
        try:
            result = await handler(request.override(tool=tool))
        except Exception as exc:
            from langgraph.errors import GraphInterrupt

            if isinstance(exc, GraphInterrupt):
                raise
            # infrastructure failure inside the tool (dead MCP server, native
            # call crash) — spec §5: a dead server surfaces as a TOOL error.
            # Strict loops keep node error-edge semantics; agentic/fallback
            # loops get an error ToolMessage so the loop can self-correct
            # instead of the whole run dying on a raw exception.
            await _finish_tool_call(
                step_id,
                status="failed",
                output=None,
                error=str(exc),
                usage=holder,
                kind=meta.get("kind"),
                source=meta.get("source"),
            )
            if self._strict_tool_errors:
                raise ToolExecutionFailed(f"tool {name!r} failed: {exc}") from exc
            return ToolMessage(
                content=f"tool {name!r} failed: {exc}",
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        finally:
            TOOL_USAGE_HOLDER.reset(token)
        is_error = isinstance(result, ToolMessage) and result.status == "error"
        from app.llm import text_from_content

        content = text_from_content(getattr(result, "content", result))
        await _finish_tool_call(
            step_id,
            status="failed" if is_error else "completed",
            output=None if is_error else content,
            error=content if is_error else None,
            usage=holder,
            kind=meta.get("kind"),
            source=meta.get("source"),
        )
        if self._strict_tool_errors and is_error:
            raise ToolExecutionFailed(f"tool {name!r} failed: {result.content}")
        return result


class SkillsRegistryMiddleware(AgentMiddleware[Any, Any]):
    """Injects exposed skills (spec §7.0): summaries into the system prompt
    and each skill as a callable capability whose handler runs the inline
    skill loop — with only its bound tools (isolation is never suspended)."""

    def __init__(self, *, mode: Literal["exposed", "full_catalog"] = "exposed") -> None:
        super().__init__()
        self._mode = mode
        self._current: dict[str, dict[str, Any]] = {}
        self._catalog_total = 0

    def _effective_full(self) -> bool:
        ctx = get_run_context()
        return self._mode == "full_catalog" or bool(ctx and ctx.flags.full_catalog)

    async def _snapshots(self) -> tuple[list[dict[str, Any]], int]:
        """Returns (snapshots, total-before-retrieval) for the catalog footer."""
        from app.registry_cache import get_cache
        from app.retrieval import apply_ambient_allowlist, apply_retrieval

        full = self._effective_full()
        records = await get_cache().skills(exposed_only=not full)
        records = apply_ambient_allowlist(records, kind="skills")
        total = len(records)
        if not full:
            records, _dropped = await apply_retrieval(records, kind="skills")
        return records, total

    def _tool_for(self, snap: dict[str, Any], name: str | None = None) -> BaseTool:
        from app.factory.worker import sanitize_tool_name

        if name is None:
            name = f"use_skill_{sanitize_tool_name(snap['name'])}"

        async def run(task: str) -> str:
            from app.orchestrator.ladder import run_inline_skill

            ctx = get_run_context()
            if ctx is not None:
                await ctx.recorder.record_route(
                    capability={"type": "direct_skill", "id": snap["id"]},
                    rung="fallback" if self._effective_full() else "direct_skill",
                    resolved_to={
                        "entity_id": snap["id"],
                        "entity_name": snap["name"],
                        "definition_version": snap.get("definition_version"),
                        "definition_hash": snap.get("definition_hash"),
                    },
                    kind="skill",
                )
            result = await run_inline_skill(snap, task, parent_step_id=CURRENT_STEP_ID.get())
            if result.get("status") != "ok":
                return f"skill failed: {result.get('error')}"
            return str(result.get("output", ""))

        return StructuredTool.from_function(
            coroutine=run,
            name=name,
            description=f"Run the {snap['name']!r} skill: {snap.get('description') or ''} "
            f"(argument: task — the concrete instruction for the skill)",
        )

    async def _refresh(self) -> list[BaseTool]:
        from app.factory.worker import sanitize_tool_name

        snaps, self._catalog_total = await self._snapshots()
        self._current = {}
        tools: list[BaseTool] = []
        for snap in snaps:
            # registry names need not be unique (only ids are) — but bound
            # tool names must be, so suffix duplicates with the record id
            name = f"use_skill_{sanitize_tool_name(snap['name'])}"
            if name in self._current:
                name = f"{name}_{str(snap.get('id', ''))[:6]}"
            tool = self._tool_for(snap, name)
            self._current[name] = snap
            tools.append(tool)
        return tools

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        from app.retrieval import catalog_footer

        tools = await self._refresh()
        lines: list[str] = []
        for tool in tools:
            snap = self._current[tool.name]
            desc = snap.get("description") or snap["name"]
            if snap.get("direct_exposure"):
                # the registry id is part of the catalog line: spin_worker's
                # contract is ids-only, so the model must be able to quote them
                lines.append(f"- {tool.name} (skill id: {snap.get('id')}): {desc}")
            else:
                # only the full-catalog fallback surfaces a non-exposed skill,
                # and only to run it inline, in the open (spec §7.0). It is not
                # composable into an ephemeral worker (§7.1 rung 4), so the line
                # withholds the id spin_worker would need to quote.
                lines.append(
                    f"- {tool.name} (fallback only — call it directly; it cannot be "
                    f"composed into an ephemeral worker): {desc}"
                )
        if len(tools) < self._catalog_total:
            # spec §7.4: a ranked slice must announce itself
            lines.append(catalog_footer("skills", len(tools), self._catalog_total))
        system = request.system_message
        section = "\n\nAvailable skills (each runs an isolated specialist loop):\n" + (
            "\n".join(lines) if lines else "(none)"
        )
        base = system.text if system is not None else ""
        request = request.override(
            tools=[*request.tools, *tools],
            system_message=SystemMessage(content=base + section),
        )
        log_catalog_call(
            "skills",
            "full_catalog" if self._effective_full() else "exposed",
            [str(s.get("id")) for s in self._current.values()],
        )
        return await handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = request.tool_call["name"]
        if name not in self._current and name.startswith("use_skill_"):
            # HITL resume replays the interrupted tool call before any model
            # call runs, so a fresh instance must resolve its registry here.
            await self._refresh()
        if name in self._current:
            snap = self._current[name]
            return await handler(request.override(tool=self._tool_for(snap, name)))
        return await handler(request)


class SubAgentsRegistryMiddleware(AgentMiddleware[Any, Any]):
    """Deepagents-style dispatch (spec §7.0): exposes dispatch tools built
    live from sub agent cards; the handler is the resolution-ladder executor.
    interrupt() raised inside the dispatched graph propagates to the parent
    for HITL; handlers are idempotent because resume replays the tool call."""

    def __init__(self) -> None:
        super().__init__()
        self._current: dict[str, dict[str, Any]] = {}

    async def _cards(self) -> list[dict[str, Any]]:
        from app.registry_cache import get_cache
        from app.retrieval import apply_ambient_allowlist, apply_retrieval

        cards = await get_cache().sub_agent_cards()
        cards = apply_ambient_allowlist(cards, kind="sub_agents")
        cards, _dropped = await apply_retrieval(cards, kind="sub_agents")
        return cards

    def _tool_for(self, card: dict[str, Any], name: str | None = None) -> BaseTool:
        from app.factory.worker import sanitize_tool_name

        if name is None:
            name = f"dispatch_{sanitize_tool_name(card['name'])}"

        async def run(task: str) -> str:
            from app.orchestrator.ladder import (
                execute_resolution,
                find_running_dispatch,
                resolve_capability,
            )

            resolution = await resolve_capability({"type": "sub_agent", "id": card["id"]})
            ctx = get_run_context()
            node_id = f"agentic:{card['name']}"
            # HITL resume replays this handler — the route was already
            # recorded before the pause when the dispatch step is still open
            replay = ctx is not None and await find_running_dispatch(ctx.run_id, node_id)
            if replay and ctx is not None:
                # the replay runs the agent as it is NOW; the catalog the run
                # froze says what it was — a difference is on the log
                from app.orchestrator.snapshot import frozen_definition_hash

                was = await frozen_definition_hash(ctx.run_id, "sub_agents", card["id"])
                if was is not None and was != resolution.definition_hash:
                    logger.warning(
                        "definition_changed_during_pause",
                        run_id=str(ctx.run_id),
                        entity=card["name"],
                        current_version=resolution.definition_version,
                    )
            if ctx is not None and not replay:
                await ctx.recorder.record_route(
                    capability={"type": "sub_agent", "id": card["id"]},
                    rung=resolution.rung,
                    resolved_to=resolution.as_route(),
                    kind=resolution.kind,
                    source=resolution.source,
                )
            result = await execute_resolution(resolution, task, node_id)
            if result.get("status") == "denied":
                # the worker's text already carries the human reviewer's verdict
                return str(result.get("output", ""))
            if result.get("status") != "ok":
                return f"sub agent failed: {result.get('error')}"
            return str(result.get("output", ""))

        return StructuredTool.from_function(
            coroutine=run,
            name=name,
            description=(
                f"Dispatch to sub agent {card['name']!r} "
                f"(skills: {', '.join(card['skills']) or 'code-defined'}): "
                f"{card.get('description') or ''} (argument: task)"
            ),
        )

    async def _refresh(self) -> list[BaseTool]:
        from app.factory.worker import sanitize_tool_name

        cards = await self._cards()
        self._current = {}
        tools: list[BaseTool] = []
        for card in cards:
            name = f"dispatch_{sanitize_tool_name(card['name'])}"
            if name in self._current:
                name = f"{name}_{card['id'][:6]}"
            tool = self._tool_for(card, name)
            self._current[name] = card
            tools.append(tool)
        return tools

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        tools = await self._refresh()
        log_catalog_call(
            "sub_agents", "exposed", [str(c.get("id")) for c in self._current.values()]
        )
        return await handler(request.override(tools=[*request.tools, *tools]))

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = request.tool_call["name"]
        if name not in self._current and name.startswith("dispatch_"):
            # HITL resume replays the interrupted tool call before any model
            # call runs, so a fresh instance must resolve its registry here.
            await self._refresh()
        if name in self._current:
            return await handler(request.override(tool=self._tool_for(self._current[name], name)))
        return await handler(request)


def build_middleware_stack(
    context: SkillLoopContext | FallbackLoopContext | AgenticLoopContext,
) -> list[AgentMiddleware[Any, Any]]:
    """One helper, used everywhere (spec §7.0)."""
    if isinstance(context, SkillLoopContext):
        return [
            SummarizationMiddleware(model=context.model),
            # +1: an N-iteration tool loop is N tool rounds plus the final answer
            ModelCallLimitMiddleware(
                run_limit=context.max_tool_iterations + 1, exit_behavior="error"
            ),
            ToolsRegistryMiddleware(
                mode="scoped",
                scoped_tool_ids=context.bound_tool_ids,
                strict_tool_errors=context.strict_tool_errors,
            ),
        ]
    if isinstance(context, FallbackLoopContext):
        return [
            SummarizationMiddleware(model=context.model),
            ModelCallLimitMiddleware(
                run_limit=context.max_tool_iterations + 1, exit_behavior="error"
            ),
            ToolsRegistryMiddleware(mode="full_catalog"),
            SkillsRegistryMiddleware(mode="full_catalog"),
        ]
    if isinstance(context, AgenticLoopContext):
        return [
            TodoListMiddleware(),
            SummarizationMiddleware(model=context.model),
            ModelCallLimitMiddleware(
                run_limit=max(context.max_tool_iterations * 3, 12), exit_behavior="error"
            ),
            ToolsRegistryMiddleware(mode="exposed"),
            SkillsRegistryMiddleware(mode="exposed"),
            SubAgentsRegistryMiddleware(),
        ]
    raise TypeError(f"unknown middleware context: {type(context).__name__}")


@contextlib.contextmanager
def current_step(step_id: UUID | None) -> Any:
    token = CURRENT_STEP_ID.set(step_id)
    try:
        yield
    finally:
        CURRENT_STEP_ID.reset(token)
