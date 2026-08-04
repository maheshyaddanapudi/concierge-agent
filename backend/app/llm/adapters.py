"""Built-in provider adapters (spec §2.1): anthropic, google_genai, openai.

Thin wrappers over LangChain provider packages, each gated by its API key env
var. Each adapter maps the normalized ModelParams onto its provider's knobs —
effort becomes the Anthropic thinking budget, the OpenAI reasoning effort, or
the Gemini thinking budget. A future custom gateway adapter implements the
same port and registers here — zero consumer changes.
"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_config
from app.llm.port import ModelInfo, ModelParams, ProviderNotConfiguredError
from app.llm.registry import model_provider

# effort → Anthropic extended-thinking budget tokens
_ANTHROPIC_THINKING_BUDGET = {"low": 1024, "medium": 8192, "high": 32768}
# effort → Gemini thinking budget tokens ('none' disables thinking)
_GEMINI_THINKING_BUDGET = {"none": 0, "low": 1024, "medium": 8192, "high": 24576}
# effort → OpenAI reasoning effort string
_OPENAI_REASONING_EFFORT = {"none": "minimal", "low": "low", "medium": "medium", "high": "high"}


def _check_params(provider: "ModelProviderBase", model: str, params: ModelParams | None) -> None:
    info = next((m for m in provider.list_models() if m.id == model), None)
    if info is not None:
        unsupported = info.unsupported_params(params)
        if unsupported:
            raise ValueError(
                f"{provider.provider_id}:{model} does not support params: {', '.join(unsupported)}"
            )


class ModelProviderBase:
    provider_id = "base"

    def list_models(self) -> list[ModelInfo]:  # pragma: no cover - overridden
        return []


@model_provider
class AnthropicProvider(ModelProviderBase):
    provider_id = "anthropic"

    def is_configured(self) -> bool:
        return bool(get_config().anthropic_api_key)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ModelInfo("claude-opus-4-6", "Claude Opus 4.6"),
            ModelInfo("claude-haiku-4-5", "Claude Haiku 4.5"),
        ]

    def get_chat_model(self, model: str, params: ModelParams | None = None) -> BaseChatModel:
        if not self.is_configured():
            raise ProviderNotConfiguredError("anthropic: ANTHROPIC_API_KEY not set")
        _check_params(self, model, params)
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {}
        if params:
            if params.effort and params.effort != "none":
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": _ANTHROPIC_THINKING_BUDGET[params.effort],
                }
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                kwargs["max_tokens"] = params.max_output_tokens
        return ChatAnthropic(model_name=model, **kwargs)


@model_provider
class GoogleGenAIProvider(ModelProviderBase):
    provider_id = "google_genai"

    def is_configured(self) -> bool:
        return bool(get_config().google_api_key)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro"),
            ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ]

    def get_chat_model(self, model: str, params: ModelParams | None = None) -> BaseChatModel:
        if not self.is_configured():
            raise ProviderNotConfiguredError("google_genai: GOOGLE_API_KEY not set")
        _check_params(self, model, params)
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs: dict[str, Any] = {}
        if params:
            if params.effort is not None:
                kwargs["thinking_budget"] = _GEMINI_THINKING_BUDGET[params.effort]
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                kwargs["max_output_tokens"] = params.max_output_tokens
        return ChatGoogleGenerativeAI(model=model, **kwargs)


@model_provider
class OpenAIProvider(ModelProviderBase):
    provider_id = "openai"

    def is_configured(self) -> bool:
        return bool(get_config().openai_api_key)

    def list_models(self) -> list[ModelInfo]:
        return [
            # reasoning family: effort supported, temperature not accepted
            ModelInfo("gpt-5", "GPT-5", supports_temperature=False),
            ModelInfo("gpt-5-mini", "GPT-5 mini", supports_temperature=False),
            # non-reasoning: temperature supported, effort not applicable
            ModelInfo("gpt-4o", "GPT-4o", supports_effort=False),
        ]

    def get_chat_model(self, model: str, params: ModelParams | None = None) -> BaseChatModel:
        if not self.is_configured():
            raise ProviderNotConfiguredError("openai: OPENAI_API_KEY not set")
        _check_params(self, model, params)
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {}
        if params:
            if params.effort is not None:
                kwargs["reasoning_effort"] = _OPENAI_REASONING_EFFORT[params.effort]
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                kwargs["max_tokens"] = params.max_output_tokens
        return ChatOpenAI(model=model, **kwargs)
