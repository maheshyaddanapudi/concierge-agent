"""First-boot default-model resolution (spec §13): with no explicit setting
stored and the code default's provider unconfigured, the seed pass picks the
first configured provider's flagship — anthropic → gemini flash → gpt-5.6
luna → openrouter qwen → the custom gateway's first model → fake. An
explicit setting is never touched."""

from collections.abc import Iterator

import pytest

from app.config import get_config
from app.db import get_session_factory
from app.models import AppSetting
from app.seed.loader import resolve_first_boot_default_model
from app.settings_store import get_setting


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_config.cache_clear()
    yield monkeypatch
    get_config.cache_clear()


async def test_fake_only_resolves_to_scripted() -> None:
    """Test env baseline: no real keys, FAKE_LLM_ENABLED=1."""
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "fake:scripted"
        assert await get_setting(session, "default_model") == "fake:scripted"


async def test_resolution_is_first_boot_only() -> None:
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "fake:scripted"
        # second call: the stored row exists now — nothing to do
        assert await resolve_first_boot_default_model(session) is None


async def test_explicit_setting_never_touched() -> None:
    async with get_session_factory()() as session:
        session.add(AppSetting(key="default_model", value={"value": "openai:gpt-5.5"}))
        await session.commit()
        assert await resolve_first_boot_default_model(session) is None
        assert await get_setting(session, "default_model") == "openai:gpt-5.5"


async def test_google_flagship_beats_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "google_genai:gemini-3.6-flash"


async def test_openai_flagship(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "openai:gpt-5.6-luna"


async def test_google_preferred_over_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "google_genai:gemini-3.6-flash"


async def test_anthropic_configured_keeps_code_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) is None
        assert await get_setting(session, "default_model") == "anthropic:claude-sonnet-4-6"
        assert await session.get(AppSetting, "default_model") is None  # no row written


async def test_openrouter_only_install_gets_a_usable_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """code_setting_ui_hardening: openrouter was missing from the preference
    list, so an install keyed only with OPENROUTER_API_KEY — the provider
    every acceptance frame in this repo was captured on — matched nothing,
    kept the unconfigured anthropic code default, and could not run a chat
    until a human opened Settings."""
    monkeypatch.delenv("FAKE_LLM_ENABLED", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "openrouter:qwen/qwen3.8-max"


async def test_openrouter_is_preferred_over_the_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "openrouter:qwen/qwen3.8-max"


async def test_custom_gateway_resolves_to_its_first_declared_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gateway's model ids are deployment-specific, so the entry carries
    no hardcoded ref — it asks the adapter."""
    monkeypatch.delenv("FAKE_LLM_ENABLED", raising=False)
    monkeypatch.setenv("CUSTOM_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("CUSTOM_GATEWAY_API_KEY", "gw-test")
    monkeypatch.setenv("CUSTOM_GATEWAY_MODELS", "house-large, house-small")
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) == "custom:house-large"


async def test_a_custom_gateway_with_no_model_list_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured but model-less: the adapter returns only its placeholder,
    which `get_chat_model` would reject — so it must not become the default."""
    monkeypatch.delenv("FAKE_LLM_ENABLED", raising=False)
    monkeypatch.setenv("CUSTOM_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("CUSTOM_GATEWAY_API_KEY", "gw-test")
    monkeypatch.delenv("CUSTOM_GATEWAY_MODELS", raising=False)
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) is None


async def test_nothing_configured_leaves_code_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_LLM_ENABLED", raising=False)
    get_config.cache_clear()
    async with get_session_factory()() as session:
        assert await resolve_first_boot_default_model(session) is None
        assert await session.get(AppSetting, "default_model") is None
