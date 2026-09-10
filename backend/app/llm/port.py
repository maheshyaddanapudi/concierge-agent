"""The ModelProvider port (spec §2.1) — the common currency is BaseChatModel.

``ModelParams`` is the normalized model configuration; each adapter maps
``effort`` to its provider's knob (Anthropic thinking budget, OpenAI reasoning
effort, Gemini thinking config). ``ModelInfo`` declares which params each
model supports; selecting an unsupported combination is rejected at save.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict

Effort = Literal["none", "low", "medium", "high"]


class ModelParams(BaseModel):
    """Normalized model configuration (spec §2.1)."""

    model_config = ConfigDict(extra="forbid")

    effort: Effort | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str
    supports_effort: bool = True
    supports_temperature: bool = True
    supports_max_output_tokens: bool = True
    # M51: a retired model stays listed so a saved reference is refused with
    # a message naming it, instead of failing mid-run as a provider 404
    deprecated: bool = False

    def unsupported_params(self, params: ModelParams | None) -> list[str]:
        """Names of params set in `params` that this model does not support."""
        if params is None:
            return []
        errors: list[str] = []
        if params.effort is not None and not self.supports_effort:
            errors.append("effort")
        if params.temperature is not None and not self.supports_temperature:
            errors.append("temperature")
        if params.max_output_tokens is not None and not self.supports_max_output_tokens:
            errors.append("max_output_tokens")
        return errors


class ProviderNotConfiguredError(RuntimeError):
    """Raised when get_chat_model is called on an unconfigured provider."""


class EmbeddingsNotSupportedError(RuntimeError):
    """Raised when get_embeddings is called on a provider without an
    embeddings API (spec §2.1 — consumers degrade to lexical-only)."""


class UnsupportedParamsError(ValueError):
    """Raised when params include options the selected model does not support."""


ProviderErrorKind = Literal["rate_limited", "timeout", "unknown_model", "provider_error"]


def classify_provider_error(exc: BaseException) -> ProviderErrorKind:
    """Name the failure class of a provider exception WITHOUT importing any
    provider SDK (spec §2.1): SDK errors expose `status_code` / `response`
    and carry telling class names. M51: a 429 is reported as rate-limiting
    (the port's retry budget already backed off), a timeout as a timeout
    (LLM_TIMEOUT_S), a 404 / "does not exist" / "deprecated" as a model
    that is no longer served — each names its cause in the run's error."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status == 429 or "ratelimit" in name or "rate limit" in text or "rate_limit" in text:
        return "rate_limited"
    if isinstance(exc, TimeoutError) or "timeout" in name or "timed out" in text:
        return "timeout"
    if (
        status == 404
        or "notfound" in name
        or any(
            marker in text
            for marker in ("does not exist", "not found", "deprecated", "retired", "no longer")
        )
    ):
        return "unknown_model"
    return "provider_error"


@runtime_checkable
class ModelProvider(Protocol):
    """A provider adapter's only job is to return a BaseChatModel."""

    provider_id: str

    def is_configured(self) -> bool: ...

    def list_models(self) -> list[ModelInfo]: ...

    def get_chat_model(self, model: str, params: ModelParams | None = None) -> BaseChatModel: ...

    def supports_embeddings(self) -> bool: ...

    async def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]: ...
