"""Egress policy for every outbound fetch (M52).

An autonomous agent that holds tools is steered by what it fetches, and
what it fetches is chosen by URLs that came from a user, a model, a card,
or a feed. This module is the one place those URLs are judged and the one
way their bodies are read:

- `check_url` applies the policy (`EGRESS_POLICY`): `public` refuses any
  target that is loopback, link-local (cloud metadata lives there),
  private, reserved, multicast or unspecified — by literal address AND
  by what the hostname resolves to — except hosts the operator names in
  `EGRESS_ALLOW_HOSTS` (suffix match), which is how an internal MCP
  server or agent is admitted; `allowlist` admits only those hosts;
  `open` keeps only the caps. Only http/https ever pass.
- `client()` builds an httpx client whose request hook re-runs the check
  on EVERY request — redirects included, hop by hop, at most five.
- `fetch_bytes` / `fetch_text` stream the body and refuse it the moment
  it exceeds the cap (`EGRESS_MAX_BYTES`), before it is ever held whole.
- `EgressError` has ONE public shape — `egress refused: <kind>` — whatever
  the cause; the URL and the upstream detail go to the log, never to the
  model or the API caller, so a refusal cannot be used to map a network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from typing import Any, Literal

import httpx
import structlog

logger = structlog.get_logger("egress")

EgressKind = Literal["denied", "too_large", "timeout", "unreachable", "status", "redirects"]
MAX_REDIRECTS = 5
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}

Resolver = Callable[[str], list[str]]
_resolver: Resolver | None = None


class EgressError(RuntimeError):
    """The fixed error shape. `kind` is the only public information. Every
    refusal is counted and logged (kind + host + a truncated detail) at
    the moment it is raised — once, wherever it happens."""

    def __init__(self, kind: EgressKind, detail: str = "", host: str | None = None) -> None:
        super().__init__(f"egress refused: {kind}")
        self.kind: EgressKind = kind
        self.detail = detail  # logged here, never surfaced
        from app import obs

        obs.EGRESS_REFUSED.labels(kind=kind).inc()
        logger.warning("egress_refused", kind=kind, host=host, detail=detail[:200])


def set_resolver(fn: Resolver | None) -> None:
    """Testing hook: replace DNS resolution."""
    global _resolver
    _resolver = fn


def _policy() -> tuple[str, list[str], int]:
    from app.config import get_config

    cfg = get_config()
    mode = (cfg.egress_policy or "public").strip().lower()
    if mode not in {"public", "allowlist", "open"}:
        mode = "public"
    hosts = [h.strip().lower() for h in (cfg.egress_allow_hosts or "").split(",") if h.strip()]
    return mode, hosts, max(int(cfg.egress_max_bytes), 1024)


def max_bytes() -> int:
    return _policy()[2]


def _is_forbidden_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return bool(
        addr.is_loopback
        or addr.is_link_local
        or addr.is_private
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _allowlisted(host: str, allow: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for entry in allow:
        if entry.startswith("."):
            if host.endswith(entry) or host == entry[1:]:
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


def _resolve(host: str) -> list[str]:
    if _resolver is not None:
        return _resolver(host)
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def check_url_static(url: str) -> None:
    """The part of the policy that needs no network: scheme, literal
    addresses, local names, the allowlist. Cheap enough for save-time
    validation at the API boundary."""
    mode, allow, _ = _policy()
    try:
        parsed = httpx.URL(url)
    except Exception as exc:  # noqa: BLE001 — any unparsable URL is refused the same way
        raise EgressError("denied", f"unparsable url: {exc}") from exc
    if parsed.scheme not in {"http", "https"}:
        raise EgressError("denied", f"scheme {parsed.scheme!r} is not http(s)", host=parsed.host)
    host = (parsed.host or "").strip("[]").lower()
    if not host:
        raise EgressError("denied", "no host")
    if mode == "open":
        return
    if mode == "allowlist":
        if not _allowlisted(host, allow):
            raise EgressError("denied", f"host {host!r} is not allowlisted", host=host)
        return
    if _allowlisted(host, allow):
        return  # public mode: the operator named this host (an internal MCP server, agent…)
    if host in _LOCAL_NAMES or host.endswith(".localhost"):
        raise EgressError("denied", f"host {host!r} is local", host=host)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return  # a name: resolved by check_url
    if _is_forbidden_address(str(literal)):
        raise EgressError("denied", f"address {host} is in a refused range", host=host)


async def check_url(url: str) -> None:
    """The full policy: the static checks plus what the name resolves to.
    Every address a hostname resolves to must pass (a name that is half
    public and half private is refused whole)."""
    check_url_static(url)
    mode, allow, _ = _policy()
    if mode != "public":
        return
    host = (httpx.URL(url).host or "").strip("[]").lower()
    if _allowlisted(host, allow):
        return  # named by the operator: admitted whatever it resolves to
    try:
        ipaddress.ip_address(host)
        return  # a literal, already judged
    except ValueError:
        pass
    try:
        addresses = await asyncio.to_thread(_resolve, host)
    except (OSError, ValueError) as exc:
        raise EgressError("unreachable", f"{host!r} does not resolve: {exc}", host=host) from exc
    if not addresses:
        raise EgressError("unreachable", f"{host!r} resolved to nothing", host=host)
    for ip in addresses:
        if _is_forbidden_address(ip):
            raise EgressError("denied", f"{host!r} resolves to {ip}, a refused range", host=host)


async def _request_hook(request: httpx.Request) -> None:
    await check_url(str(request.url))  # a refusal counts and logs itself


def client(
    *,
    timeout: float = 20.0,
    follow_redirects: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """An httpx client under the policy: every request — every redirect
    hop — is checked in the request hook before it leaves the process."""
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        max_redirects=MAX_REDIRECTS,
        event_hooks={"request": [_request_hook]},
        transport=transport,
    )


def mcp_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """The MCP SDK's `httpx_client_factory` shape, under the policy."""
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout if timeout is not None else httpx.Timeout(30.0),
        auth=auth,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        event_hooks={"request": [_request_hook]},
    )


def _map_transport_error(exc: BaseException, url: str) -> EgressError:
    if isinstance(exc, EgressError):
        return exc
    host = httpx.URL(url).host
    if isinstance(exc, httpx.TooManyRedirects):
        return EgressError("redirects", f"{url}: {exc}", host=host)
    if isinstance(exc, httpx.TimeoutException):
        return EgressError("timeout", f"{url}: {exc}", host=host)
    if isinstance(exc, httpx.HTTPStatusError):
        return EgressError("status", f"{url}: HTTP {exc.response.status_code}", host=host)
    return EgressError("unreachable", f"{url}: {type(exc).__name__}: {exc}", host=host)


async def fetch_bytes(
    http: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int | None = None,
    method: str = "GET",
    **kwargs: Any,
) -> tuple[bytes, httpx.Response]:
    """Stream the body under the cap. The static policy is applied here too
    so a caller-supplied client (tests inject one) still cannot be pointed
    at a literal private address."""
    cap = max_bytes if max_bytes is not None else max_bytes_default()
    check_url_static(url)
    try:
        async with http.stream(method, url, **kwargs) as resp:
            resp.raise_for_status()
            host = httpx.URL(url).host
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > cap:
                raise EgressError(
                    "too_large", f"{url}: content-length {declared} > {cap}", host=host
                )
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > cap:
                    raise EgressError("too_large", f"{url}: body exceeded {cap} bytes", host=host)
                chunks.append(chunk)
            return b"".join(chunks), resp
    except EgressError:
        raise  # already counted and logged when it was raised
    except Exception as exc:  # noqa: BLE001 — every transport failure takes the fixed shape
        raise _map_transport_error(exc, url) from exc


def max_bytes_default() -> int:
    return max_bytes()


async def fetch_text(
    http: httpx.AsyncClient, url: str, *, max_bytes: int | None = None, **kwargs: Any
) -> str:
    body, resp = await fetch_bytes(http, url, max_bytes=max_bytes, **kwargs)
    encoding = resp.encoding or "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def fetch_json(
    http: httpx.AsyncClient, url: str, *, max_bytes: int | None = None, **kwargs: Any
) -> Any:
    import json

    text = await fetch_text(http, url, max_bytes=max_bytes, **kwargs)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise EgressError("status", f"{url}: body is not JSON") from exc
