"""Observability (spec §10): structlog JSON, Prometheus metrics, OTel spans,
per-run LangSmith tracer. One shared label set on every span/log/metric:
{run_id, step_id, tier, kind, source, entity_id, entity_name, model, effort,
input_tokens, output_tokens, duration_ms, status}.
"""

import logging
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

from app.config import get_config

# ── structured logs ──────────────────────────────────────────────


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=False,
    )


# ── metrics (spec §10): counters + histograms labeled tier/kind/source ─

RUNS_TOTAL = Counter("concierge_runs_total", "Runs started", ["mode", "status"])
STEPS_TOTAL = Counter(
    "concierge_steps_total", "Run steps recorded", ["tier", "kind", "source", "status"]
)
TOOL_CALLS_TOTAL = Counter(
    "concierge_tool_calls_total", "Tool calls executed", ["kind", "source", "status"]
)
ERRORS_TOTAL = Counter("concierge_errors_total", "Errors", ["tier", "kind", "source"])
RUN_DURATION = Histogram("concierge_run_duration_seconds", "Run duration", ["mode", "status"])
STEP_DURATION = Histogram(
    "concierge_step_duration_seconds", "Step duration", ["tier", "kind", "source"]
)
STEP_TOKENS = Histogram(
    "concierge_step_tokens", "Tokens per step", ["tier", "kind", "source", "direction"]
)

# ── OpenTelemetry ────────────────────────────────────────────────

_otel_configured = False


def get_tracer() -> trace.Tracer:
    global _otel_configured
    if not _otel_configured:
        provider = TracerProvider(resource=Resource.create({"service.name": "concierge-agent"}))
        endpoint = get_config().otel_exporter_otlp_endpoint
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _otel_configured = True
    return trace.get_tracer("concierge-agent")


# ── LangSmith (spec §10): per-run tracer from live settings ──────


def build_langsmith_callbacks(settings: dict[str, Any], run_id: str) -> list[Any]:
    """Constructed per run from settings and injected via callbacks — not
    process env — so enabling/pointing LangSmith needs no restart. The API
    key alone stays env-only."""
    if not settings.get("langsmith_enabled"):
        return []
    api_key = get_config().langsmith_api_key
    if not api_key:
        return []
    try:
        from langchain_core.tracers.langchain import LangChainTracer
        from langsmith import Client

        client = Client(
            api_url=str(settings.get("langsmith_endpoint") or "https://api.smith.langchain.com"),
            api_key=api_key,
        )
        tracer = LangChainTracer(
            project_name=str(settings.get("langsmith_project") or "concierge-agent"),
            client=client,
        )
        # run_id metadata cross-references PG traces and OTel spans
        return [tracer]
    except Exception:  # noqa: BLE001 - observability must never break runs
        structlog.get_logger("obs").warning("langsmith_tracer_failed", run_id=run_id)
        return []


def label_set(
    *,
    run_id: str,
    step_id: str | None = None,
    tier: str,
    kind: str | None = None,
    source: str | None = None,
    entity_id: str | None = None,
    entity_name: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """The §10 label set, attached to every span and log line."""
    return {
        "run_id": run_id,
        "step_id": step_id,
        "tier": tier,
        "kind": kind,
        "source": source,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "model": model,
        "effort": effort,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "status": status,
    }
