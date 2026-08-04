"""Model provider abstraction (spec §2.1).

The ONLY module tree allowed to import provider SDKs or LangChain provider
packages. Everything else calls ``get_model("provider:model")`` and receives a
``BaseChatModel``.
"""

from app.llm.port import (
    ModelInfo,
    ModelParams,
    ModelProvider,
    ProviderNotConfiguredError,
    UnsupportedParamsError,
)
from app.llm.registry import (
    UnknownProviderError,
    get_model,
    get_provider,
    list_providers,
    model_provider,
    validate_model_selection,
)

__all__ = [
    "ModelInfo",
    "ModelParams",
    "ModelProvider",
    "ProviderNotConfiguredError",
    "UnknownProviderError",
    "UnsupportedParamsError",
    "get_model",
    "get_provider",
    "list_providers",
    "model_provider",
    "validate_model_selection",
]
