"""Provider-call metrics at the port (M53, arch-M7).

Every chat model leaves `get_model()` carrying one LangChain callback
handler that times each call and classifies its outcome — through
LangChain's callback abstraction only, never a provider SDK (spec §2.1).
The series:

- `concierge_llm_calls_total{provider, model, status}`
- `concierge_llm_latency_seconds{provider, model, status}`

`status` is `ok` or the M51 provider-error class (`rate_limited`,
`timeout`, `unknown_model`, `provider_error`). A call that the SDK retried
internally (LLM_MAX_RETRIES) counts once, with the outcome the run saw —
sustained rate-limiting shows as latency first and as `rate_limited` once
the retry budget is spent.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from app import obs
from app.llm.port import classify_provider_error


class LlmMetricsHandler(BaseCallbackHandler):
    """Sync handler, run inline — cheap enough for every call, works for
    sync and async invocations alike."""

    run_inline = True
    raise_error = False

    def __init__(self, provider_id: str, model_id: str) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self._starts: dict[UUID, float] = {}

    def on_chat_model_start(
        self, serialized: Any, messages: Any, *, run_id: UUID, **kw: Any
    ) -> None:
        self._starts[run_id] = time.monotonic()

    def on_llm_start(self, serialized: Any, prompts: Any, *, run_id: UUID, **kw: Any) -> None:
        self._starts[run_id] = time.monotonic()

    def on_llm_end(self, response: Any, *, run_id: UUID, **kw: Any) -> None:
        self._observe(run_id, "ok")

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kw: Any) -> None:
        self._observe(run_id, classify_provider_error(error))

    def _observe(self, run_id: UUID, status: str) -> None:
        started = self._starts.pop(run_id, None)
        elapsed = time.monotonic() - started if started is not None else 0.0
        labels = {"provider": self.provider_id, "model": self.model_id, "status": status}
        obs.LLM_CALLS.labels(**labels).inc()
        obs.LLM_LATENCY.labels(**labels).observe(elapsed)


_HANDLERS: dict[tuple[str, str], LlmMetricsHandler] = {}


def instrument(model: BaseChatModel, provider_id: str, model_id: str) -> BaseChatModel:
    """Attach the metrics handler to a freshly built model (idempotent)."""
    key = (provider_id, model_id)
    handler = _HANDLERS.get(key)
    if handler is None:
        handler = _HANDLERS[key] = LlmMetricsHandler(provider_id, model_id)
    existing = list(model.callbacks or []) if isinstance(model.callbacks, list) else []
    if handler not in existing:
        model.callbacks = [*existing, handler]
    return model
