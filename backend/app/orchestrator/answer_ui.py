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

from app.llm import get_model
from app.prompts import load_prompt

logger = structlog.get_logger("orchestrator.answer_ui")

A2UI_VERSION = "v0.9"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
SURFACE_ID = "answer"

ComponentType = Literal[
    "card", "text", "stat", "table", "list", "badge", "divider", "link", "sources"
]


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
    model_ref: str, task: str, answer: str, callbacks: list[Any]
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """Returns ({"a2ui": messages}, usage). Never raises — failure → (None, usage)."""
    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        model = get_model(model_ref)
        prompt = load_prompt("answer_ui").replace("{task}", task).replace("{answer}", answer)
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
        return {"a2ui": to_a2ui_messages(parsed)}, usage
    except Exception as exc:  # noqa: BLE001 - failure-safe by spec
        logger.warning("answer_ui_generation_failed", error=str(exc))
        return None, usage
