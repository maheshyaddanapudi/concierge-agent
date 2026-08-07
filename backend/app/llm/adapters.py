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
from app.llm.port import (
    EmbeddingsNotSupportedError,
    ModelInfo,
    ModelParams,
    ProviderNotConfiguredError,
)
from app.llm.registry import model_provider

# effort → Anthropic extended-thinking budget tokens
_ANTHROPIC_THINKING_BUDGET = {"low": 1024, "medium": 8192, "high": 32768}
_CLAUDE5_PREFIXES = ("claude-sonnet-5", "claude-opus-5", "claude-fable-5")
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

    # embeddings (spec §2.1/§7.4): opt-in per adapter; default is unsupported
    def supports_embeddings(self) -> bool:
        return False

    async def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        raise EmbeddingsNotSupportedError(f"provider {self.provider_id!r} has no embeddings API")


@model_provider
class AnthropicProvider(ModelProviderBase):
    provider_id = "anthropic"

    def is_configured(self) -> bool:
        return bool(get_config().anthropic_api_key)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("claude-sonnet-5", "Claude Sonnet 5"),
            ModelInfo("claude-opus-5", "Claude Opus 5"),
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
                if model.startswith(_CLAUDE5_PREFIXES):
                    # the Claude 5 family replaces budgeted thinking with
                    # adaptive thinking steered by output_config.effort
                    kwargs["thinking"] = {"type": "adaptive"}
                    kwargs["output_config"] = {"effort": params.effort}
                else:
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
            ModelInfo("gemini-3.6-flash", "Gemini 3.6 Flash"),
            ModelInfo("gemini-3.5-flash", "Gemini 3.5 Flash"),
            ModelInfo("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
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

    def supports_embeddings(self) -> bool:
        return True

    async def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("google_genai: GOOGLE_API_KEY not set")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return await GoogleGenerativeAIEmbeddings(model=model).aembed_documents(texts)


@model_provider
class OpenAIProvider(ModelProviderBase):
    provider_id = "openai"

    def is_configured(self) -> bool:
        return bool(get_config().openai_api_key)

    def list_models(self) -> list[ModelInfo]:
        return [
            # reasoning family: effort supported, temperature not accepted
            ModelInfo("gpt-5.6-terra", "GPT-5.6 Terra", supports_temperature=False),
            ModelInfo("gpt-5.6-luna", "GPT-5.6 Luna", supports_temperature=False),
            ModelInfo("gpt-5.5", "GPT-5.5", supports_temperature=False),
            ModelInfo("gpt-5.4", "GPT-5.4", supports_temperature=False),
            ModelInfo("gpt-5.4-mini", "GPT-5.4 mini", supports_temperature=False),
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
                # current OpenAI reasoning models reject function tools +
                # reasoning_effort on /v1/chat/completions — reasoning runs
                # ride the Responses API instead (same BaseChatModel out)
                kwargs["use_responses_api"] = True
                kwargs["output_version"] = "responses/v1"
                kwargs["reasoning"] = {"effort": _OPENAI_REASONING_EFFORT[params.effort]}
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                kwargs["max_tokens"] = params.max_output_tokens
        return ChatOpenAI(model=model, **kwargs)

    def supports_embeddings(self) -> bool:
        return True

    async def get_embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("openai: OPENAI_API_KEY not set")
        from langchain_openai import OpenAIEmbeddings

        return await OpenAIEmbeddings(model=model).aembed_documents(texts)
