"""Static native tools (spec §5b).

`summarize-and-structure` is a single-node LangGraph subgraph exposed as a
tool: one LLM call that converts raw text into a structured JSON summary.
It proves the subgraph-as-tool path alongside MCP tools in the same skill.
"""

from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import AliasChoices, BaseModel, Field

from app.db import get_session_factory
from app.llm import ModelParams, get_model
from app.native.provider import native_tool
from app.prompts import load_prompt


class StructuredSummary(BaseModel):
    """Structured output schema for summarize-and-structure."""

    title: str = Field(description="short descriptive title")
    summary: str = Field(description="faithful 2-4 sentence summary")
    key_points: list[str] = Field(description="3-7 most important points")
    entities: list[str] = Field(description="named people/organizations/products")


class _SummarizeState(TypedDict):
    text: str
    result: dict[str, Any]


async def _resolve_default_model() -> tuple[str, ModelParams | None]:
    from app.settings_store import get_setting

    async with get_session_factory()() as session:
        ref = await get_setting(session, "default_model")
        raw = await get_setting(session, "default_model_params")
    params = ModelParams.model_validate(raw) if raw else None
    return str(ref), params


def build_summarize_graph() -> Any:
    async def summarize_node(state: _SummarizeState, config: RunnableConfig) -> dict[str, Any]:
        ref, params = await _resolve_default_model()
        model = get_model(ref, params).with_structured_output(StructuredSummary)
        prompt = load_prompt("summarize_and_structure").format(text=state["text"])
        try:
            result = await model.ainvoke(prompt, config=config)
        except Exception as exc:
            # strict schema + one repair retry (same pattern as planner
            # validation, spec §7.1): feed the validation errors back once
            repair = (
                f"{prompt}\n\nYour previous attempt failed schema validation:\n{exc}\n"
                "Return a JSON object matching the schema EXACTLY — key_points and "
                "entities MUST be JSON arrays of strings."
            )
            result = await model.ainvoke(repair, config=config)
        assert isinstance(result, StructuredSummary)
        return {"result": result.model_dump()}

    graph = StateGraph(_SummarizeState)
    graph.add_node("summarize", summarize_node)
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


@native_tool(
    "summarize-and-structure",
    "Convert raw text into a structured JSON summary (title, summary, key points, entities).",
)
async def summarize_and_structure(
    text: str, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """Invoke the single-node subgraph; callbacks in `config` capture usage."""
    graph = build_summarize_graph()
    out: dict[str, Any] = await graph.ainvoke({"text": text}, config=config)
    return dict(out["result"])


class _ChartSeries(BaseModel):
    # Chart.js-style `label`/`data` accepted as validation aliases so a
    # first call in that common convention succeeds instead of burning a
    # repair round-trip; canonical dump stays `name`/`values` (the renderer
    # contract in ChartSvg.tsx)
    name: str = Field("", validation_alias=AliasChoices("name", "label"))
    values: list[float] = Field(validation_alias=AliasChoices("values", "data"))


class _ChartSpec(BaseModel):
    """render_chart args (spec §5b): data the caller actually holds."""

    kind: Literal["bar", "line", "pie"]
    title: str = ""
    labels: list[str]
    series: list[_ChartSeries]


@native_tool(
    "render_chart",
    "Validate and normalize a chart specification (bar, line, or pie) from data "
    "you already hold — labels plus one or more numeric series. Each series is "
    'an object {"name": str, "values": [numbers]} whose values align 1:1 with '
    "labels. Use ONLY with real data from the conversation or tool results, "
    "never invented numbers. The normalized spec is rendered as a chart in the "
    "final answer panel.",
)
async def render_chart(
    kind: str, labels: list[str], series: list[_ChartSeries], title: str = ""
) -> str:
    """Pure validation/normalization — no model call, no side effects."""
    spec = _ChartSpec.model_validate(
        {"kind": kind, "title": title, "labels": labels, "series": series}
    )
    for entry in spec.series:
        if len(entry.values) != len(spec.labels):
            raise ValueError(
                f"series {entry.name or '?'!r} has {len(entry.values)} values "
                f"for {len(spec.labels)} labels"
            )
    return spec.model_dump_json()
