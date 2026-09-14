"""Three defects a documentation pass turned up by measuring instead of
reading (docs-hardening wave).

S1  The ambient webhook URL was not a known secret. A Slack/Teams-shaped
    webhook carries its token in the URL PATH, so neither the userinfo
    parser nor the `key=value` shape patterns caught it — and httpx puts the
    full URL into the exception `raise_for_status` raises, which the channel
    ledger stores and the Inbox renders.

S3  `AuthMiddleware` guarded every method including OPTIONS. A browser
    strips credentials from a CORS preflight by definition, so the preflight
    401'd and the real request was never sent — making a cross-origin admin
    UI impossible under exactly the configuration the hardening checklist
    recommended (auth on, FRONTEND_ORIGIN pinned).

A1  `stalled` was missing from the SSE terminal set while `obs.py` and the
    frontend both treated it as terminal, so the server never closed a
    stalled run's stream and had no branch to resolve one from the record.
"""

from typing import Any
from uuid import uuid4

import pytest

from app.config import get_config
from app.db import get_session_factory
from app.models import Conversation, Run

pytestmark = pytest.mark.anyio


class TestWebhookUrlIsASecret:
    def test_the_webhook_url_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app import sanitize

        url = "https://hooks.example.com/services/T00/B00/SuperSecretTokenValue123"
        monkeypatch.setenv("AMBIENT_WEBHOOK_URL", url)
        get_config.cache_clear()
        sanitize._secret_cache = None
        try:
            out = sanitize.sanitize_error(f"POST failed to {url} -> 500")
            assert out is not None
            assert "SuperSecretTokenValue123" not in out, "the webhook token survived"
            assert url not in out
        finally:
            sanitize._secret_cache = None
            get_config.cache_clear()

    def test_an_unset_webhook_url_changes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A None/blank candidate must not turn into a redaction of ''."""
        from app import sanitize

        monkeypatch.delenv("AMBIENT_WEBHOOK_URL", raising=False)
        get_config.cache_clear()
        sanitize._secret_cache = None
        try:
            text = "POST failed to https://hooks.example.com/x -> 500"
            assert sanitize.sanitize_error(text) == text
        finally:
            sanitize._secret_cache = None
            get_config.cache_clear()


class TestCorsPreflightIsNotGuarded:
    async def test_options_preflight_is_not_401ed_when_auth_is_on(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTH_ENABLED", "1")
        get_config.cache_clear()
        try:
            resp = await client.options(
                "/api/v1/settings",
                headers={
                    "Origin": "https://admin.example.com",
                    "Access-Control-Request-Method": "PATCH",
                },
            )
            assert resp.status_code != 401, "the preflight was rejected; no CORS request can follow"
        finally:
            get_config.cache_clear()

    async def test_a_real_request_is_still_guarded(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exempting OPTIONS must not exempt anything that carries data."""
        monkeypatch.setenv("AUTH_ENABLED", "1")
        get_config.cache_clear()
        try:
            resp = await client.patch("/api/v1/settings", json={"max_plan_steps": 3})
            assert resp.status_code == 401, resp.text
        finally:
            get_config.cache_clear()


class TestStalledIsTerminalOnTheStream:
    def test_stalled_counts_as_terminal(self) -> None:
        from app.api.chat import _TERMINAL, _is_terminal

        assert "stalled" in _TERMINAL
        assert _is_terminal({"type": "run_status", "payload": {"status": "stalled"}})

    def test_the_obs_set_and_the_stream_set_agree(self) -> None:
        """They disagreed, which is how the gap survived: each looked right
        on its own."""
        from app import obs
        from app.api.chat import _TERMINAL

        assert set(obs.TERMINAL_RUN_STATUSES) == _TERMINAL

    async def test_a_stalled_run_resolves_from_the_record(self) -> None:
        """A client reconnecting after the in-process events are gone used to
        get nothing at all for a stalled run, and hung."""
        from app.api.chat import synthesize_terminal_events

        async with get_session_factory()() as session:
            conv = Conversation(id=uuid4(), title="c")
            session.add(conv)
            await session.flush()
            run = Run(
                id=uuid4(),
                conversation_id=conv.id,
                chat_message="q",
                status="stalled",
                error="no heartbeat for 300s",
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

        events = synthesize_terminal_events(run, after=7)
        assert events, "a stalled run synthesised no terminal events"
        kinds = [e["type"] for e in events]
        assert "run_status" in kinds
        assert any(e.get("payload", {}).get("status") == "stalled" for e in events)
        assert any("heartbeat" in str(e.get("payload", {}).get("message", "")) for e in events)
        # the sequence continues from the client's Last-Event-ID
        assert [e["seq"] for e in events] == list(range(8, 8 + len(events)))
