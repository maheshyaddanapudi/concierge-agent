"""Static native tools (spec §5b).

`summarize-and-structure` is a single-node LangGraph subgraph exposed as a
tool: one LLM call that converts raw text into a structured JSON summary.
It proves the subgraph-as-tool path alongside MCP tools in the same skill.
"""

import json
from typing import Any, Literal, TypedDict

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db import get_session_factory
from app.llm import ModelParams, get_model
from app.native.provider import native_tool
from app.prompts import load_prompt

logger = structlog.get_logger("native.tools")


class StructuredSummary(BaseModel):
    """Structured output schema for summarize-and-structure."""

    title: str = Field(description="short descriptive title")
    summary: str = Field(description="faithful 2-4 sentence summary")
    key_points: list[str] = Field(description="3-7 most important points")
    entities: list[str] = Field(description="named people/organizations/products")


# the fetched body a summarize call may carry; the fence truncates past it
_SUMMARIZE_MAX_CHARS = 20000


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
        from app import untrusted

        ref, params = await _resolve_default_model()
        model = get_model(ref, params).with_structured_output(StructuredSummary)
        # M52: this is the CANONICAL untrusted path — `web-research` chains
        # fetch → summarize, so the text is whatever a fetched page said, and
        # it used to arrive unfenced. A page's instructions were read as
        # instructions, and the summary they produced was trusted downstream.
        prompt = untrusted.render(
            load_prompt("summarize_and_structure"),
            mode="replace",
            body_var="text",
            body=str(state["text"]),
            max_chars=_SUMMARIZE_MAX_CHARS,
        )
        try:
            result = await model.ainvoke(prompt, config=config)
        except Exception as exc:  # noqa: BLE001 — parser/validation error types vary by adapter; one repair retry
            # strict schema + one repair retry (same pattern as planner
            # validation, spec §7.1): feed the validation errors back once
            repair = (
                f"{prompt}\n\nYour previous attempt failed schema validation:\n{exc}\n"
                "Return a JSON object matching the schema EXACTLY — key_points and "
                "entities MUST be JSON arrays of strings."
            )
            result = await model.ainvoke(repair, config=config)
        if not isinstance(result, StructuredSummary):
            raise TypeError(f"expected StructuredSummary, got {type(result).__name__}")
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
    # NaN/Infinity are refused at the schema boundary (hardening): a
    # non-finite number survives pydantic's default float validation, rides
    # into the run's JSONB `charts` column, and Postgres then rejects the
    # bare `NaN` as invalid JSON — the commit raises and an already-produced
    # final answer is lost. Nothing non-finite may get past this model.
    model_config = ConfigDict(allow_inf_nan=False)

    # Chart.js-style `label`/`data` accepted as validation aliases so a
    # first call in that common convention succeeds instead of burning a
    # repair round-trip; canonical dump stays `name`/`values` (the renderer
    # contract in ChartSvg.tsx)
    name: str = Field("", validation_alias=AliasChoices("name", "label"))
    values: list[float] = Field(
        default_factory=list, validation_alias=AliasChoices("values", "data")
    )
    # scatter/bubble points: [x, y] or [x, y, size] per point
    points: list[list[float]] | None = None
    # combo charts: how this series draws
    render: Literal["bar", "line"] | None = None


ChartKind = Literal[
    "bar",
    "hbar",
    "stacked_bar",
    "stacked_bar_100",
    "line",
    "area",
    "stacked_area",
    "pie",
    "donut",
    "histogram",
    "funnel",
    "waterfall",
    "lollipop",
    "gauge",
    "sparkline",
    "scatter",
    "bubble",
    "candlestick",
    "boxplot",
    "gantt",
    "combo",
]

# kinds where per-series values align 1:1 with labels (the default contract)
_ALIGNED_KINDS = {
    "bar",
    "hbar",
    "stacked_bar",
    "stacked_bar_100",
    "line",
    "area",
    "stacked_area",
    "pie",
    "donut",
    "histogram",
    "funnel",
    "waterfall",
    "lollipop",
    "combo",
    "candlestick",
    "boxplot",
}
_NAMED_SERIES_KINDS = {
    "candlestick": ["open", "high", "low", "close"],
    "boxplot": ["min", "q1", "median", "q3", "max"],
}


class _ChartSpec(BaseModel):
    """render_chart args (spec §5b): data the caller actually holds.

    The single validation boundary for every chart that reaches the
    renderer — the native tool, the formatter's own chart components and
    the tool charts replayed out of the run steps all go through it, so
    one contract governs one renderer (`validate_chart_spec`)."""

    model_config = ConfigDict(allow_inf_nan=False)

    kind: ChartKind
    title: str = ""
    labels: list[str]
    series: list[_ChartSeries]
    # gantt only: [startISO, endISO] per label, e.g. ["2026-08-01", "2026-08-05"]
    ranges: list[list[str]] | None = None

    @model_validator(mode="after")
    def _kind_shape(self) -> "_ChartSpec":
        if self.kind in {"scatter", "bubble"}:
            need = 3 if self.kind == "bubble" else 2
            if not self.series or not all(s.points for s in self.series):
                raise ValueError(
                    f"{self.kind} needs points ([x, y{', size' if need == 3 else ''}]) on every series"
                )
            for s in self.series:
                for p in s.points or []:
                    if len(p) < need:
                        raise ValueError(f"{self.kind} points need {need} numbers each")
            return self
        if self.kind == "gauge":
            if len(self.series) != 1 or len(self.series[0].values) != 2:
                raise ValueError("gauge needs exactly one series with [value, max]")
            return self
        if self.kind == "sparkline":
            if not self.series or not self.series[0].values:
                raise ValueError("sparkline needs one series of values")
            return self
        if self.kind == "gantt":
            if not self.ranges or len(self.ranges) != len(self.labels):
                raise ValueError("gantt needs ranges ([startISO, endISO]) aligned 1:1 with labels")
            for r in self.ranges:
                if len(r) != 2:
                    raise ValueError("each gantt range is [start, end]")
            return self
        expected = _NAMED_SERIES_KINDS.get(self.kind)
        if expected:
            names = sorted(s.name.lower() for s in self.series)
            if names != sorted(expected):
                raise ValueError(f"{self.kind} needs exactly these series: {', '.join(expected)}")
        if (
            self.kind in {"funnel", "waterfall", "pie", "donut", "histogram"}
            and len(self.series) > 1
        ):
            # single-series kinds: extra series are almost always a mistake
            raise ValueError(f"{self.kind} takes exactly one series")
        if self.kind in _ALIGNED_KINDS:
            for entry in self.series:
                if len(entry.values) != len(self.labels):
                    raise ValueError(
                        f"series {entry.name or '?'!r} has {len(entry.values)} values "
                        f"for {len(self.labels)} labels"
                    )
        return self


def _error_summary(exc: ValidationError, limit: int = 3) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'spec'}: {err['msg']}"
        for err in exc.errors()[:limit]
    )


def _nonfinite_locations(exc: ValidationError) -> list[str]:
    """Where a NaN/Infinity was refused (pydantic's `finite_number`)."""
    return [
        ".".join(str(p) for p in err["loc"])
        for err in exc.errors()
        if err["type"] == "finite_number"
    ]


def validate_chart_spec(spec: Any, *, source: str) -> dict[str, Any] | None:
    """Put an arbitrary chart spec through the renderer's contract.

    Every chart that reaches `ChartSvg` must pass here, whoever produced
    it — the render_chart tool validated its own args from the start, but
    the formatter's chart components and the tool charts collected from
    run steps used to be waved through on a "has a kind and a series"
    glance. Returns the canonical (normalized) spec, or None with a log
    line naming what was dropped and why."""
    if not isinstance(spec, dict):
        logger.info("chart_spec_dropped", source=source, reason="not a chart object")
        return None
    try:
        validated = _ChartSpec.model_validate(spec)
    except ValidationError as exc:
        logger.info(
            "chart_spec_dropped",
            source=source,
            kind=spec.get("kind"),
            title=spec.get("title"),
            reason=_error_summary(exc),
        )
        return None
    return validated.model_dump(exclude_none=True)


@native_tool(
    "render_chart",
    "Validate and normalize a chart specification from data you already hold — "
    "rendered as a real chart in the final answer panel. Kinds: bar / hbar "
    "(horizontal) / stacked_bar / stacked_bar_100 (normalized %), line / area / "
    "stacked_area (trends), pie / donut (shares, one series), histogram "
    "(pre-binned ONLY: bin-range labels + counts — never bin raw values "
    "yourself), funnel (ordered stages, one series), waterfall (signed deltas, "
    "one series), lollipop, gauge (one series [value, max]), sparkline (tiny "
    "trend), scatter / bubble (per-series points [x,y] / [x,y,size]), "
    "candlestick (four series named open/high/low/close), boxplot (five series "
    "named min/q1/median/q3/max — pre-computed only), gantt (ranges: "
    '[startISO, endISO] per label), combo (per-series render: "bar"|"line"). '
    'Default shape: {"name": str, "values": [numbers]} aligned 1:1 with labels. '
    "Use ONLY real data from the conversation or tool results, never invented "
    "numbers.",
)
async def render_chart(
    kind: str,
    labels: list[str],
    series: list[_ChartSeries],
    title: str = "",
    ranges: list[list[str]] | None = None,
) -> str:
    """Pure validation/normalization — no model call, no side effects."""
    try:
        spec = _ChartSpec.model_validate(
            {"kind": kind, "title": title, "labels": labels, "series": series, "ranges": ranges}
        )
    except ValidationError as exc:
        bad = _nonfinite_locations(exc)
        if not bad:
            raise  # shape errors stay hard errors — the loop repairs them
        # a non-finite number is not a shape mistake the loop can read off a
        # traceback: name the exact points so the next call is a clean repair,
        # and make sure NaN/Infinity never reaches the run's JSONB charts
        logger.info("chart_spec_dropped", source="render_chart", kind=kind, reason="non-finite")
        return json.dumps(
            {
                "status": "chart rejected — nothing was rendered",
                "error": (
                    "non-finite number(s) at "
                    + ", ".join(bad)
                    + ". NaN and Infinity cannot be stored or drawn. Re-send the "
                    "chart with finite numbers only (drop the offending points, or "
                    "supply the real value)."
                ),
            }
        )
    # the tool result is the model's only observation of what happened — say
    # explicitly that a real chart WILL render, or models hedge with ASCII
    # duplicates of the same data in their prose answer
    return json.dumps(
        {
            "status": (
                "chart accepted — it will be rendered as a real chart in the "
                "answer panel; do not draw an ASCII/text version of this data, "
                "and refer to the chart WITHOUT positional words like 'above' "
                "or 'below' (its position varies by view)"
            ),
            "spec": spec.model_dump(exclude_none=True),
        }
    )
