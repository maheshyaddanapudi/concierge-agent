"""Inbound request limits — the mirror of `app.egress`'s outbound caps.

Two things, both unconditional:

- **A body size cap.** Nothing bounded a request body anywhere: not the
  application, not uvicorn's command line, not nginx. `POST /chat`'s
  message, a HITL note, a skill's instructions, `PATCH /settings`, a
  credential map and the eval upload were all unbounded, so one large POST
  was an out-of-memory kill of the single process that serves everything.
  The cap is checked on the declared length AND while the body streams, so
  a chunked request without a `Content-Length` cannot walk past it.

- **A rate limit that does not depend on authentication.** The token bucket
  existed, but it lived inside `AuthMiddleware` behind `provider.enabled()`,
  so the shipped configuration — auth dark — had no limit at all. This one
  runs always, keyed on the caller's address; when auth is on, the
  per-principal bucket still applies on top of it.

Both are env configuration (`MAX_REQUEST_BYTES`, `RATE_LIMIT_*` settings for
the shape), not something the API can raise about itself mid-flight.
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger("limits")

# the streaming health/metrics surfaces and the SSE streams carry no body and
# must never be throttled — a chat stream holds one connection for a run
_EXEMPT_PREFIXES = ("/health", "/ready", "/metrics")
_STREAM_SUFFIXES = ("/stream", "/ambient/stream")


def _too_large(limit: int) -> JSONResponse:
    return JSONResponse(
        {"detail": f"request body too large (limit {limit} bytes)"}, status_code=413
    )


class LimitsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        from app.config import get_config

        path = request.url.path
        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)  # type: ignore[no-any-return]

        limit = int(get_config().max_request_bytes)
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > _limit_for(path, limit):
                        return _too_large(_limit_for(path, limit))
                except ValueError:
                    return JSONResponse({"detail": "invalid Content-Length"}, status_code=400)
            else:
                # chunked: cap while it streams, so an undeclared body cannot
                # walk past the limit one chunk at a time
                capped = _limit_for(path, limit)
                total = 0
                chunks: list[bytes] = []
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > capped:
                        return _too_large(capped)
                    chunks.append(chunk)
                body = b"".join(chunks)

                async def _replay() -> dict[str, Any]:
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = _replay

        if not await _within_rate(request):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        return await call_next(request)  # type: ignore[no-any-return]


def _limit_for(path: str, default: int) -> int:
    """The eval dataset upload gets the larger upload cap; everything else
    gets the JSON body cap."""
    from app.config import get_config

    if path.endswith("/datasets") and "/evals/" in path:
        return int(get_config().max_upload_bytes)
    return default


async def _within_rate(request: Request) -> bool:
    """One shared bucket per caller address. Failure of the shared store is
    availability, not a closed door — the same rule the authenticated
    limiter follows."""
    if any(request.url.path.endswith(s) for s in _STREAM_SUFFIXES):
        return True
    from app import ratelimit
    from app.registry_cache import get_cache

    try:
        burst = float(await get_cache().setting("rate_limit_burst"))
        per_s = float(await get_cache().setting("rate_limit_per_s"))
    except Exception:  # noqa: BLE001 — a settings hiccup keeps the defaults
        burst, per_s = 120.0, 10.0
    host = request.client.host if request.client else "-"
    try:
        return await ratelimit.allow(f"addr:{host}", burst, per_s)
    except Exception as exc:  # noqa: BLE001 — availability over a limit
        logger.warning("rate_limit_store_unavailable", error=str(exc)[:200])
        return True
