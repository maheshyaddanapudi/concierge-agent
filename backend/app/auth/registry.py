"""The auth provider registry (spec §20.2, M55): `@auth_provider` registers
a class by `provider_id`; `AUTH_PROVIDER` selects the active one (default
`builtin`); `AUTH_PROVIDER_MODULE` names a module to import first so a
fork's provider registers itself from its own file. `get_auth_provider()`
is the only way the core reaches a provider."""

from __future__ import annotations

import importlib
from typing import Any

from app.auth.port import AuthProvider

_PROVIDERS: dict[str, AuthProvider] = {}
_active: AuthProvider | None = None


class UnknownAuthProviderError(ValueError):
    pass


def auth_provider[T: type[Any]](cls: T) -> T:
    """Class decorator: instantiate and register by `provider_id`."""
    instance = cls()
    _PROVIDERS[str(instance.provider_id)] = instance
    return cls


def list_auth_providers() -> list[AuthProvider]:
    _ensure_builtin()
    return list(_PROVIDERS.values())


def reset_auth_provider() -> None:
    """Testing hook: forget the resolved provider (registrations stay)."""
    global _active
    _active = None


def _ensure_builtin() -> None:
    if "builtin" not in _PROVIDERS:
        importlib.import_module("app.auth.builtin")


def get_auth_provider() -> AuthProvider:
    """The active provider, resolved once from the environment."""
    global _active
    if _active is not None:
        return _active
    from app.config import get_config

    cfg = get_config()
    _ensure_builtin()
    module = cfg.auth_provider_module
    if module:
        importlib.import_module(module)
    wanted = cfg.auth_provider or "builtin"
    provider = _PROVIDERS.get(wanted)
    if provider is None:
        raise UnknownAuthProviderError(
            f"AUTH_PROVIDER={wanted!r} is not registered — registered: {sorted(_PROVIDERS)}; "
            "set AUTH_PROVIDER_MODULE to the module that defines it"
        )
    _active = provider
    return provider
