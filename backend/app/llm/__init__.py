"""Model provider abstraction (spec §2.1).

The ONLY module tree allowed to import provider SDKs or LangChain provider
packages. Everything else calls ``get_model("provider:model")`` and receives a
``BaseChatModel``.
"""

from app.llm.content import text_from_content, thinking_from_content
from app.llm.port import (
    EmbeddingsNotSupportedError,
    ModelInfo,
    ModelParams,
    ModelProvider,
    ProviderNotConfiguredError,
    UnsupportedParamsError,
    classify_provider_error,
)
from app.llm.registry import (
    UnknownProviderError,
    get_embeddings,
    get_model,
    get_provider,
    list_providers,
    model_provider,
    validate_embedding_selection,
    validate_model_selection,
)

__all__ = [
    "text_from_content",
    "thinking_from_content",
    "EmbeddingsNotSupportedError",
    "ModelInfo",
    "ModelParams",
    "ModelProvider",
    "ProviderNotConfiguredError",
    "UnknownProviderError",
    "UnsupportedParamsError",
    "classify_provider_error",
    "get_embeddings",
    "get_model",
    "get_provider",
    "list_providers",
    "model_provider",
    "validate_embedding_selection",
    "validate_model_selection",
]
