"""Delivery channels (spec §18.4 — milestone M29).

A channel adapter registry behind the `ambient_channels` setting (per-tier
routing, validated against registered adapters). `in_app` is the outbox
itself and always exists; `email` renders a batch as ONE SMTP message
(SMTP_* env-only — no secrets in the DB); `webhook` POSTs one JSON envelope
to AMBIENT_WEBHOOK_URL (the SMS/push-gateway shape). Every external send is
recorded per channel on the delivery row (`external` jsonb); a channel
failure logs and never blocks the in-app outbox.

The same dispatch hook feeds the global ambient SSE stream: one event per
delivered row, consumed by `/api/v1/ambient/stream` subscribers (the
in-app toast). With `ambient_channels` empty the dispatch is a no-op and
delivery behavior stays byte-identical to M23–M25.
"""

import asyncio
import itertools
import smtplib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
import structlog

from app.db import get_session_factory
from app.models import Delivery

logger = structlog.get_logger("ambient")

DELIVERY_MODES = {"interrupt", "notify", "digest"}

# channel adapter contract: (mode, delivered rows) -> None; raise = failure
ChannelAdapter = Callable[[str, list[Delivery]], Awaitable[None]]
_ADAPTERS: dict[str, ChannelAdapter] = {}

_http_client_factory: Callable[[], httpx.AsyncClient] | None = None


def set_http_client_factory(fn: Callable[[], httpx.AsyncClient] | None) -> None:
    global _http_client_factory
    _http_client_factory = fn


def _client() -> httpx.AsyncClient:
    if _http_client_factory is not None:
        return _http_client_factory()
    from app import egress

    # M52: the operator's sink is still an outbound fetch — same policy,
    # and a POST never follows a redirect (it would resend the envelope)
    return egress.client(timeout=15.0, follow_redirects=False)


def register_channel_adapter(name: str, fn: ChannelAdapter | None) -> None:
    if fn is None:
        _ADAPTERS.pop(name, None)
    else:
        _ADAPTERS[name] = fn


def registered_channels() -> set[str]:
    """`in_app` is the outbox itself — always present, never an adapter."""
    return {"in_app"} | set(_ADAPTERS)


# ── native adapters (spec §18.4) ─────────────────────────────────────


def _item_lines(rows: list[Delivery]) -> str:
    lines = []
    for row in rows:
        lines.append(f"• [{row.category} · urgency {row.urgency}] {row.title}")
        if row.body:
            lines.append(f"  {row.body}")
    return "\n".join(lines)


async def email_channel(mode: str, rows: list[Delivery]) -> None:
    """ONE message per batch over SMTP; SMTP_HOST/PORT/USER/PASSWORD/FROM/TO
    are env-only (spec §13) — an unset host is a config error, not silence."""
    from app.config import get_config

    cfg = get_config()
    if not cfg.smtp_host or not cfg.smtp_from or not cfg.smtp_to:
        raise RuntimeError("SMTP is not configured (SMTP_HOST/SMTP_FROM/SMTP_TO)")
    msg = EmailMessage()
    msg["From"] = cfg.smtp_from
    msg["To"] = cfg.smtp_to
    msg["Subject"] = f"[concierge] ambient {mode}: {len(rows)} item(s)"
    msg.set_content(_item_lines(rows) + "\n\n— concierge ambient delivery\n")

    def _send() -> None:
        with smtplib.SMTP(cfg.smtp_host or "", cfg.smtp_port, timeout=15) as smtp:
            if cfg.smtp_user and cfg.smtp_password:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)

    await asyncio.to_thread(_send)


async def webhook_channel(mode: str, rows: list[Delivery]) -> None:
    """One JSON envelope per batch to AMBIENT_WEBHOOK_URL — the generic
    SMS/push-gateway shape; any provider bridge terminates there."""
    from app.config import get_config

    url = get_config().ambient_webhook_url
    if not url:
        raise RuntimeError("webhook channel is not configured (AMBIENT_WEBHOOK_URL)")
    envelope = {
        "kind": "ambient_delivery",
        "mode": mode,
        "items": [
            {
                "id": str(row.id),
                "category": row.category,
                "tier": row.tier,
                "urgency": row.urgency,
                "title": row.title,
                "body": row.body,
            }
            for row in rows
        ],
    }
    async with _client() as client:
        resp = await client.post(url, json=envelope)
        resp.raise_for_status()


def register_native_channels() -> None:
    """Idempotent; called from the app lifespan."""
    register_channel_adapter("email", email_channel)
    register_channel_adapter("webhook", webhook_channel)


# ── the SSE broadcast hub (spec §18.4 toast) ─────────────────────────

_subscribers: dict[int, asyncio.Queue[dict[str, Any]]] = {}
_next_sub = 0
# keepalive cadence for the SSE stream; each tick also re-checks
# ambient_enabled so a stream closes soon after ambient goes dark
STREAM_KEEPALIVE_S = 15.0


def subscribe_stream() -> tuple[int, asyncio.Queue[dict[str, Any]]]:
    global _next_sub
    _next_sub += 1
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
    _subscribers[_next_sub] = queue
    return _next_sub, queue


def unsubscribe_stream(sub_id: int) -> None:
    _subscribers.pop(sub_id, None)


def stream_subscriber_count() -> int:
    """This process's share of the §18.4 pursuit oracle: how many
    subscribers `_publish` fans out to here. Since M54 the toast reaches
    every replica, so the oracle proper is `audience()` — this count plus
    the other live replicas' (their heartbeat rows carry it)."""
    return len(_subscribers)


_EVENT_SEQ = itertools.count(1)


def _fan_local(event: dict[str, Any]) -> None:
    for queue in list(_subscribers.values()):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:  # a stalled consumer never blocks the tick
            continue


def _event(mode: str, row: Delivery, now: str) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "mode": mode,
        "tier": row.tier,
        "urgency": row.urgency,
        "category": row.category,
        "title": row.title,
        "at": now,
    }


def _publish(mode: str, rows: list[Delivery]) -> list[dict[str, Any]]:
    """Fan a batch to THIS process's subscribers; returns the events so the
    caller can announce them to the fleet (M54)."""
    now = datetime.now(UTC).isoformat()
    events = [_event(mode, row, now) for row in rows]
    if _subscribers:
        for event in events:
            # M53: a per-process sequence is the stream's `id:` line
            _fan_local({"seq": next(_EVENT_SEQ), **event})
    return events


async def publish(mode: str, rows: list[Delivery]) -> None:
    """M54 (spec §18.9, scale-B1): the toast reaches every replica's
    subscribers — local fan-out, then one control-channel announcement per
    delivery that every OTHER replica re-fans (`fan_in`), origin-tagged so
    the announcing replica ignores its own."""
    from app import control

    for event in _publish(mode, rows):
        await control.notify("delivery", **event)


def fan_in(message: dict[str, Any]) -> None:
    """A delivery announced by another replica: give it a local sequence
    and hand it to this process's subscribers."""
    if not _subscribers:
        return
    event = {
        "seq": next(_EVENT_SEQ),
        **{k: message.get(k) for k in ("id", "mode", "tier", "urgency", "category", "title", "at")},
    }
    _fan_local(event)


async def audience() -> int:
    """The §18.4 pursuit oracle across the fleet (M54): this process's
    subscribers plus every other live replica's — the literal audience of
    the toast `publish` just sent. Falls back to the local count if the
    fleet table cannot be read."""
    local = stream_subscriber_count()
    try:
        from app.replica import cluster_audience

        return await cluster_audience(local)
    except Exception as exc:  # noqa: BLE001 — the local count is the floor, never less
        logger.warning("ambient_audience_fallback", error=str(exc)[:200])
        return local


# ── the dispatch hook (called by every flush path) ───────────────────


async def _record_send(rows: list[Delivery], channel: str, entry: dict[str, Any]) -> None:
    async with get_session_factory()() as session:
        for row in rows:
            fresh = await session.get(Delivery, row.id)
            if fresh is None:
                continue
            fresh.external = {**(fresh.external or {}), channel: entry}
        await session.commit()


# the real-time modes: these are the ones a human was meant to see AS THEY
# HAPPENED. A digest reaching an empty room is its normal condition, not a
# failure, so it is never marked unseen (spec §18.4, M42)
_REALTIME_MODES = {"interrupt", "notify"}


def _in_app_outcome(mode: str, watchers: int) -> dict[str, Any] | None:
    """M42: the truth when the in-app broadcast reached nobody.

    Recorded ONLY on the lossy path — the happy path leaves `external` null,
    so byte-identity at defaults is preserved (spec §18.4). This is an
    outcome record, never a send to retry (M51)."""
    if mode not in _REALTIME_MODES or watchers > 0:
        return None
    return {"ok": False, "error": "no subscriber", "at": datetime.now(UTC).isoformat()}


def _pursue(pursuit: str, watchers: int) -> bool:
    """Should the external channels fire for a batch the in-app hub just
    reached `watchers` subscribers with? (spec §17.5/§18.4, M41)

    - `always` — presence-blind, the pre-M41 behavior and the default
    - `away`   — only when the toast reached nobody
    - `off`    — never; in-app is the whole delivery
    """
    if pursuit == "off":
        return False
    if pursuit == "away":
        return watchers == 0
    return True  # 'always', and any unknown value fails safe to it


MAX_SEND_ATTEMPTS = 4  # M51: then the channel entry is dead-lettered
_SEND_BACKOFF_S = (60, 300, 1800)  # after attempt 1, 2, 3+
_RETRY_BATCH = 20
_RETRY_WINDOW_DAYS = 7


def _send_entry(
    prior: dict[str, Any] | None, ok: bool, error: str | None, now: datetime
) -> dict[str, Any]:
    """One channel's ledger entry: attempt counter, next attempt with
    backoff, dead-letter flag (M51). `ok` resets the retry state."""
    from app.sanitize import sanitize_error

    attempts = int((prior or {}).get("attempts") or 0) + 1
    entry: dict[str, Any] = {
        "ok": ok,
        "error": None if ok else (sanitize_error(error) or "unknown error")[:500],
        "at": now.isoformat(),
        "attempts": attempts,
        "next_attempt_at": None,
        "dead": False,
    }
    if not ok:
        if attempts >= MAX_SEND_ATTEMPTS:
            entry["dead"] = True
        else:
            backoff = _SEND_BACKOFF_S[min(attempts - 1, len(_SEND_BACKOFF_S) - 1)]
            entry["next_attempt_at"] = (now + timedelta(seconds=backoff)).isoformat()
    return entry


async def _send_one(name: str, mode: str, rows: list[Delivery]) -> tuple[bool, str | None]:
    adapter = _ADAPTERS.get(name)
    if adapter is None:
        return False, f"channel {name!r} is not registered"
    try:
        await adapter(mode, rows)
    except Exception as exc:  # noqa: BLE001 — never blocks the outbox
        return False, str(exc)[:500]
    return True, None


async def dispatch_delivered(
    mode: str, rows: list[Delivery], *, record: bool = True
) -> dict[str, dict[str, Any]]:
    """Fan a just-delivered batch out: SSE stream always, external channels
    per the `ambient_channels` routing. Failures are ledgered, logged, and
    never raised — the in-app outbox is already the source of truth.
    M51: returns the per-channel ledger entries (attempt counter, next
    attempt, dead flag); with `record=False` the caller writes them in its
    own transaction (dispatch-then-commit in the flush)."""
    if not rows:
        return {}
    # sample the oracle BEFORE publishing: this count is precisely the
    # audience `publish` is about to reach (spec §18.4, M41) — since M54
    # the fleet's audience, because the toast is fanned to every replica
    watchers = await audience()
    await publish(mode, rows)
    from app.registry_cache import get_cache

    routing = dict(await get_cache().setting("ambient_channels") or {})
    names = [str(n) for n in (routing.get(mode) or []) if n != "in_app"]
    entries: dict[str, dict[str, Any]] = {}
    # §17.5 pursuit: a routing modifier over the EXTERNAL half only — the
    # in-app outbox row and its toast above are already decided and sent
    in_app = _in_app_outcome(mode, watchers)
    if in_app is not None:
        entries["in_app"] = in_app
        logger.info(
            "ambient_delivered_unseen",
            tier="ambient",
            kind="deliver",
            mode=mode,
            count=len(rows),
            delivery_ids=[str(r.id) for r in rows],
        )
        if record:
            await _record_send(rows, "in_app", in_app)
    pursuit = str(await get_cache().setting("ambient_pursuit") or "always")
    if names and not _pursue(pursuit, watchers):
        logger.info(
            "ambient_pursuit_held",
            tier="ambient",
            kind="deliver",
            mode=mode,
            pursuit=pursuit,
            watchers=watchers,
            channels=names,
        )
        return entries
    from app import obs

    for name in names:
        ok, error = await _send_one(name, mode, rows)
        entry = _send_entry(None, ok, error, datetime.now(UTC))
        if not ok:
            logger.warning(
                "ambient_channel_failed",
                tier="ambient",
                kind="deliver",
                channel=name,
                error=entry.get("error"),
                attempts=entry["attempts"],
                next_attempt_at=entry["next_attempt_at"],
            )
        entries[name] = entry
        if record:
            await _record_send(rows, name, entry)
        obs.AMBIENT_OPS.labels(kind="channel", status=f"{name}_{'ok' if ok else 'error'}").inc()
        obs.DELIVERY_SENDS.labels(channel=name, status="ok" if ok else "retry").inc()
    return entries


async def retry_external_sends(now: datetime | None = None, batch: int = _RETRY_BATCH) -> int:
    """M51: re-send failed external channel entries whose backoff has
    elapsed, at most `batch` sends per tick; an entry that has exhausted
    MAX_SEND_ATTEMPTS is dead-lettered and never retried. Returns sends
    attempted."""
    now = now or datetime.now(UTC)
    from sqlalchemy import select

    from app import obs

    async with get_session_factory()() as session:
        rows = list(
            (
                await session.execute(
                    select(Delivery)
                    .where(
                        Delivery.external.isnot(None),
                        Delivery.delivered_at.isnot(None),
                        Delivery.delivered_at >= now - timedelta(days=_RETRY_WINDOW_DAYS),
                    )
                    .order_by(Delivery.delivered_at.desc())
                    .limit(500)
                )
            ).scalars()
        )
    attempted = 0
    for row in rows:
        if attempted >= batch:
            break
        for name, prior in dict(row.external or {}).items():
            if name == "in_app" or not isinstance(prior, dict):
                continue
            if prior.get("ok") or prior.get("dead"):
                continue
            due = prior.get("next_attempt_at")
            if not due or datetime.fromisoformat(str(due)) > now:
                continue
            ok, error = await _send_one(name, str(row.channel or "notify"), [row])
            entry = _send_entry(prior, ok, error, now)
            await _record_send([row], name, entry)
            attempted += 1
            obs.DELIVERY_SENDS.labels(
                channel=name, status="ok" if ok else ("dead" if entry["dead"] else "retry")
            ).inc()
            logger.info(
                "ambient_channel_retry",
                tier="ambient",
                kind="deliver",
                channel=name,
                ok=ok,
                attempts=entry["attempts"],
                dead=entry["dead"],
            )
            if attempted >= batch:
                break
    return attempted
