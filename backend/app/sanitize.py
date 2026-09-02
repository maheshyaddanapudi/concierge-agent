"""One exception-text sanitizer (M52).

Provider SDKs, MCP transports and HTTP clients put the request they failed
on into the exception they raise — headers, tokens, URLs with credentials.
Before any error text is persisted (a run's `error`, a step's `error`, an
MCP server's or remote agent's `last_error`, a routine's `status_reason`,
a delivery's channel ledger) or returned in an HTTP response, it passes
through `sanitize_error`. The structlog processor applies the same pass to
every string in every log line.

Two layers: the secret VALUES this process knows (every key-shaped config
field, the credentials of the record being handled) are replaced
literally; then credential SHAPES are replaced by pattern — bearer
tokens, well-known key prefixes, `key=value` pairs whose key names a
secret, and URL userinfo.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

REDACTED = "[redacted]"
_MIN_SECRET_LEN = 6

_SHAPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # scheme://user:password@host → scheme://[redacted]@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^/\s:@]*):([^/\s@]+)@"), rf"\1{REDACTED}@"),
    # Authorization: Bearer <token>, "Bearer abc" anywhere
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), rf"\1 {REDACTED}"),
    # well-known key prefixes
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}"), REDACTED),
    # key=value / key: value pairs whose key names a secret
    (
        re.compile(
            r"(?i)\b(api[_\-]?key|x-api-key|secret|password|passwd|pwd|token|access[_\-]?token"
            r"|refresh[_\-]?token|authorization|auth)(\s*[:=]\s*)([\"']?)([^\s\"',;&)]+)"
        ),
        rf"\1\2\3{REDACTED}",
    ),
]

_secret_cache: tuple[str, ...] | None = None


def reset_cache() -> None:
    global _secret_cache
    _secret_cache = None


def _url_password(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlsplit(url).password
    except ValueError:
        return None


def secret_values() -> tuple[str, ...]:
    """Every secret this process knows from config, longest first (so a
    secret that contains another is replaced whole)."""
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    from app.config import get_config

    cfg = get_config()
    candidates = [
        cfg.anthropic_api_key,
        cfg.google_api_key,
        cfg.openai_api_key,
        cfg.openrouter_api_key,
        cfg.langsmith_api_key,
        cfg.smtp_password,
        cfg.custom_gateway_api_key,
        _url_password(cfg.redis_url),
        _url_password(cfg.database_url),
    ]
    values = sorted(
        {c for c in candidates if isinstance(c, str) and len(c) >= _MIN_SECRET_LEN},
        key=len,
        reverse=True,
    )
    _secret_cache = tuple(values)
    return _secret_cache


def sanitize_error(text: str | None, *, extra_secrets: Iterable[str] = ()) -> str | None:
    """Redact known secret values and credential shapes. None stays None."""
    if text is None:
        return None
    out = str(text)
    extras = sorted(
        {s for s in extra_secrets if isinstance(s, str) and len(s) >= _MIN_SECRET_LEN},
        key=len,
        reverse=True,
    )
    for value in (*extras, *secret_values()):
        if value in out:
            out = out.replace(value, REDACTED)
    for pattern, replacement in _SHAPE_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_error(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_sanitize_value(v) for v in value)
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: every string in the event, however nested."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str | dict | list | tuple):
            event_dict[key] = _sanitize_value(value)
    return event_dict
