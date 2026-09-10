"""Per-model price table (M53 cost model).

USD per one million tokens, (input, output). Resolution order for a
`provider:model` reference:

1. the operator's `model_prices` setting (§3.7) — always wins;
2. a price the provider adapter reports (OpenRouter publishes one per
   routed model; `refresh_provider_prices()` pulls it hourly);
3. the built-in reference table below.

A model none of those know is UNPRICED: its tokens are reported, never
guessed, and the run shows `cost_priced=false`. The built-in figures are
reference values for the models the adapters list — verify them against
your invoice and override in Settings → Cost; the fake provider is free by
definition.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger("pricing")

Price = tuple[float, float]

DEFAULT_PRICES: dict[str, Price] = {
    "anthropic:claude-sonnet-4-6": (3.0, 15.0),
    "anthropic:claude-opus-4-6": (15.0, 75.0),
    "anthropic:claude-haiku-4-5": (1.0, 5.0),
    # the Claude 5 family is listed at the 4.x tier of its size class —
    # a reference figure, not a quote
    "anthropic:claude-sonnet-5": (3.0, 15.0),
    "anthropic:claude-opus-5": (15.0, 75.0),
    "google_genai:gemini-2.5-pro": (1.25, 10.0),
    "google_genai:gemini-2.5-flash": (0.30, 2.50),
    "google_genai:gemini-3.1-flash-lite": (0.10, 0.40),
    "google_genai:gemini-3.5-flash": (0.30, 2.50),
    "google_genai:gemini-3.6-flash": (0.30, 2.50),
    "openai:gpt-5": (1.25, 10.0),
    "openai:gpt-5-mini": (0.25, 2.0),
    "fake:scripted": (0.0, 0.0),
}


def _override(overrides: dict[str, Any] | None, ref: str) -> Price | None:
    if not overrides:
        return None
    row = overrides.get(ref)
    if not isinstance(row, dict):
        return None
    try:
        return (float(row.get("input_per_m", 0.0)), float(row.get("output_per_m", 0.0)))
    except (TypeError, ValueError):
        return None


def _provider_price(ref: str) -> Price | None:
    from app.llm.registry import get_provider, parse_model_ref

    try:
        provider_id, model = parse_model_ref(ref)
        provider = get_provider(provider_id)
    except ValueError:
        return None
    reporter = getattr(provider, "price_for", None)
    if reporter is None:
        return None
    price = reporter(model)
    return (float(price[0]), float(price[1])) if price else None


def price_for(ref: str, overrides: dict[str, Any] | None = None) -> Price | None:
    """(input, output) USD per 1M tokens, or None when nobody knows."""
    return _override(overrides, ref) or _provider_price(ref) or DEFAULT_PRICES.get(ref)


def cost_usd(
    ref: str, input_tokens: int, output_tokens: int, overrides: dict[str, Any] | None = None
) -> float | None:
    price = price_for(ref, overrides)
    if price is None:
        return None
    per_in, per_out = price
    return (max(input_tokens, 0) * per_in + max(output_tokens, 0) * per_out) / 1_000_000


def price_source(ref: str, overrides: dict[str, Any] | None = None) -> str | None:
    """Where a price came from: override | provider | builtin | None."""
    if _override(overrides, ref) is not None:
        return "override"
    if _provider_price(ref) is not None:
        return "provider"
    if ref in DEFAULT_PRICES:
        return "builtin"
    return None


async def refresh_provider_prices() -> dict[str, int]:
    """Ask every adapter that publishes prices to refresh them (hourly from
    the periodic loop; once at startup). Never raises."""
    from app.llm.registry import list_providers

    out: dict[str, int] = {}
    for provider in list_providers():
        refresh = getattr(provider, "refresh_prices", None)
        if refresh is None:
            continue
        try:
            out[provider.provider_id] = int(await refresh())
        except Exception as exc:  # noqa: BLE001 — a price feed outage must never break a run
            logger.warning(
                "provider_prices_refresh_failed",
                provider=provider.provider_id,
                error=str(exc)[:200],
            )
    return out
