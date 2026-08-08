"""Model-generated declarative answer UI (spec §7.1 `answer_ui`).

Two stages, by design:
1. The model generates a compact whitelisted component tree via structured
   output through the provider port — reliable on every adapter.
2. A deterministic translator converts it into **A2UI v0.9 protocol
   messages** (createSurface + updateComponents, literal values, basic
   catalog) consumed by the official @a2ui/react renderer.

Failure-safe by contract: anything invalid is dropped silently — the
streamed text answer is always the source of truth.
"""

from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from app.llm import ModelParams, get_model
from app.prompts import load_prompt

logger = structlog.get_logger("orchestrator.answer_ui")

A2UI_VERSION = "v0.9"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
SURFACE_ID = "answer"

ComponentType = Literal[
    "card", "text", "stat", "table", "list", "badge", "divider", "link", "sources", "chart"
]


class UiSeries(BaseModel):
    name: str | None = None
    values: list[float] = Field(default_factory=list)


class UiComponent(BaseModel):
    """One whitelisted component of the model-facing schema."""

    type: ComponentType
    title: str | None = None
    markdown: str | None = None
    label: str | None = None
    value: str | None = None
    hint: str | None = None
    columns: list[str] | None = None
    rows: list[list[str]] | None = None
    items: list[str] | None = None
    ordered: bool | None = None
    tone: Literal["neutral", "success", "warning", "danger"] | None = None
    url: str | None = None
    urls: list[str] | None = None
    children: list["UiComponent"] | None = None
    # chart (spec §7.1): data extracted from the answer, never invented
    chart_kind: Literal["bar", "line", "pie"] | None = None
    labels: list[str] | None = None
    series: list[UiSeries] | None = None
    # chart placement by reference: index into the run's tool-produced
    # charts — places an existing chart at this position instead of
    # re-emitting its data
    ref: int | None = None


class AnswerUi(BaseModel):
    components: list[UiComponent] = Field(default_factory=list)


class _A2uiBuilder:
    def __init__(self) -> None:
        self.components: list[dict[str, Any]] = []
        self._seq = 0

    def add(self, component: str, **props: Any) -> str:
        self._seq += 1
        cid = f"c{self._seq}"
        self.components.append({"id": cid, "component": component, **props})
        return cid

    def text(self, text: str, variant: str | None = None) -> str:
        props: dict[str, Any] = {"text": text}
        if variant:
            props["variant"] = variant
        return self.add("Text", **props)

    def column(self, children: list[str]) -> str:
        return self.add("Column", children=children)

    def emit(self, node: UiComponent) -> str | None:
        if node.type == "text":
            return self.text(node.markdown or node.label or "")
        if node.type == "card":
            child_ids = [cid for c in (node.children or []) if (cid := self.emit(c)) is not None]
            if node.title:
                child_ids.insert(0, self.text(f"**{node.title}**"))
            return self.add("Card", child=self.column(child_ids))
        if node.type == "stat":
            ids = [self.text(node.value or "", variant="h3"), self.text(node.label or "")]
            if node.hint:
                ids.append(self.text(f"_{node.hint}_"))
            return self.column(ids)
        if node.type == "table":
            rows: list[str] = []
            if node.columns:
                rows.append(
                    self.add(
                        "Row",
                        children=[self.text(f"**{c}**") for c in node.columns],
                    )
                )
            for row in node.rows or []:
                rows.append(self.add("Row", children=[self.text(str(v)) for v in row]))
            return self.column(rows)
        if node.type == "list":
            bullets = [
                self.text(f"{i + 1}. {item}" if node.ordered else f"• {item}")
                for i, item in enumerate(node.items or [])
            ]
            return self.add("List", children=bullets)
        if node.type == "badge":
            return self.text(f"**[{node.label or ''}]**")
        if node.type == "divider":
            return self.add("Divider")
        if node.type == "link":
            return self.text(f"{node.label or node.url or ''} — {node.url or ''}")
        if node.type == "sources":
            ids = [self.text("**Sources**")]
            ids += [self.text(f"• {u}") for u in node.urls or []]
            return self.column(ids)
        return None  # unknown types are ignored, never errored


def extract_charts(ui: AnswerUi) -> list[dict[str, Any]]:
    """Chart components render via the app's own themed SVG component
    (spec §7.1) — normalized specs, split out of the A2UI stream."""
    charts: list[dict[str, Any]] = []
    for c in ui.components:
        if c.type != "chart" or not c.chart_kind or not c.series:
            continue
        labels = [str(x) for x in (c.labels or [])]
        series = [
            {"name": s.name or "", "values": [float(v) for v in s.values]}
            for s in c.series
            if s.values
        ]
        if not series:
            continue
        charts.append(
            {"kind": c.chart_kind, "title": c.title or "", "labels": labels, "series": series}
        )
    return charts


def build_blocks(ui: AnswerUi, tool_chart_count: int) -> list[dict[str, Any]]:
    """Ordered render blocks preserving the formatter's chart placement
    (spec §8.5): consecutive non-chart components become one a2ui segment;
    a chart component becomes a chart block at that exact position —
    {"chart": spec} for data charts, {"tool_chart_ref": i} for placements
    of tool-produced charts. Invalid or repeated refs are dropped (the
    renderer's bottom slot remains the safety net for unplaced charts)."""
    blocks: list[dict[str, Any]] = []
    group: list[UiComponent] = []
    seen_refs: set[int] = set()

    def flush() -> None:
        nonlocal group
        if group:
            blocks.append({"a2ui": to_a2ui_messages(AnswerUi(components=group))})
            group = []

    for c in ui.components:
        if c.type != "chart":
            group.append(c)
            continue
        if c.ref is not None:
            if 0 <= c.ref < tool_chart_count and c.ref not in seen_refs:
                flush()
                seen_refs.add(c.ref)
                blocks.append({"tool_chart_ref": c.ref})
            continue
        if c.chart_kind and c.series:
            spec = extract_charts(AnswerUi(components=[c]))
            if spec:
                flush()
                blocks.append({"chart": spec[0]})
    flush()
    return blocks


def compute_coverage(answer: str, ui: AnswerUi) -> int:
    """Deterministic content-coverage percent (spec §7.1): what fraction of
    the raw answer's hard tokens — numbers, URLs, inline-code spans —
    survived into the structured artifact. An instrument, never a gate;
    an answer with no hard tokens scores 100 by definition."""
    import re

    numbers = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?", answer)
    urls = re.findall(r"https?://[^\s)\]>\"']+", answer)
    code = re.findall(r"`([^`\n]+)`", answer)
    tokens = {t.rstrip(".,;:") for t in (*numbers, *urls, *code) if t.strip()}
    if not tokens:
        return 100
    rendered = ui.model_dump_json()
    kept = sum(1 for t in tokens if t in rendered)
    return round(100 * kept / len(tokens))


def to_a2ui_messages(ui: AnswerUi) -> list[dict[str, Any]]:
    """Deterministic translation to A2UI v0.9 protocol messages."""
    builder = _A2uiBuilder()
    top_ids = [cid for c in ui.components if (cid := builder.emit(c)) is not None]
    builder.components.append({"id": "root", "component": "Column", "children": top_ids})
    return [
        {
            "version": A2UI_VERSION,
            "createSurface": {"surfaceId": SURFACE_ID, "catalogId": BASIC_CATALOG_ID},
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {"surfaceId": SURFACE_ID, "components": builder.components},
        },
    ]


async def generate_answer_ui(
    model_ref: str,
    task: str,
    answer: str,
    callbacks: list[Any],
    *,
    model_params: ModelParams | None = None,
    presentation: str = "raw_first",
    tool_charts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """The formatter call (spec §7.1): transform the canonical answer into
    the structured artifact. Returns ({"a2ui", "charts"?, "presentation",
    "coverage"}, usage). Never raises — failure → (None, usage), fail-open."""
    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        from app.registry_cache import get_cache

        charts_enabled = bool(await get_cache().setting("answer_ui_charts_enabled"))
        model = get_model(model_ref, model_params)
        prompt = load_prompt("formatter").replace("{task}", task).replace("{answer}", answer)
        chart_rules = (
            '- chart {title?, chart_kind: "bar"|"line"|"pie", labels: [..], '
            "series: [{name?, values: [numbers]}]} — ONLY when the answer contains "
            "genuinely comparative or trending numbers; the data MUST be extracted "
            "from the answer text, never computed or invented; prefer a table unless "
            "a chart clearly helps. PLACEMENT MATTERS: put each chart component at "
            "the exact position in your component sequence where the surrounding "
            "text discusses that data — next to its narrative, not dumped at the "
            "start or end."
            if charts_enabled
            else ""
        )
        prompt = prompt.replace("{chart_rules}", chart_rules)
        existing = ""
        if tool_charts and charts_enabled:
            listing = "; ".join(
                f'{i}: {c.get("title") or c.get("kind", "chart")!r}'
                for i, c in enumerate(tool_charts)
            )
            existing = (
                f"\nCharts already produced by tools during this run: {listing}. "
                "Place each one exactly once at the position where the text discusses "
                'its data, using {"type": "chart", "ref": <index>} — a ref places the '
                "existing chart there; NEVER re-emit its data as a new chart component. "
                "Any chart you leave unplaced still renders after the document."
            )
        elif tool_charts:
            existing = (
                "\nCharts already produced by tools during this run will be rendered "
                "alongside your output — do NOT re-emit them as chart components."
            )
        prompt = prompt.replace("{existing_charts}", existing)
        structured = model.with_structured_output(AnswerUi, include_raw=True)
        result: dict[str, Any] = await structured.ainvoke(  # type: ignore[assignment]
            prompt, config={"callbacks": callbacks}
        )
        meta = getattr(result.get("raw"), "usage_metadata", None)
        if meta:
            usage["input_tokens"] = meta.get("input_tokens", 0)
            usage["output_tokens"] = meta.get("output_tokens", 0)
        parsed = result.get("parsed")
        if parsed is None or not parsed.components:
            return None, usage
        if not charts_enabled:
            parsed.components = [c for c in parsed.components if c.type != "chart"]
            if not parsed.components:
                return None, usage
        payload: dict[str, Any] = {
            "a2ui": to_a2ui_messages(parsed),
            "presentation": presentation,
            "coverage": compute_coverage(answer, parsed),
        }
        charts = extract_charts(parsed) if charts_enabled else []
        if charts:
            payload["charts"] = charts
        if charts_enabled:
            blocks = build_blocks(parsed, len(tool_charts or []))
            # blocks only earn their keep when a chart actually sits mid-flow
            if any("chart" in b or "tool_chart_ref" in b for b in blocks):
                payload["blocks"] = blocks
        return payload, usage
    except Exception as exc:  # noqa: BLE001 - failure-safe by spec
        logger.warning("formatter_generation_failed", error=str(exc))
        return None, usage
