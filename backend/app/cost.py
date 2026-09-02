"""Cost model + the shared spend ceiling (M53).

Per-run cost is computed from the usage the platform already captures
(`run_steps.model` + tokens per step, `runs.total_*` for the rollup): each
step is priced at ITS model, and whatever the run totals hold beyond the
stepped tokens — the formatter's call lands on the run, not on a step — is
priced at the run's presentation model (`formatter_model`, else
`default_model`). A token nobody can price is reported as unpriced, never
guessed.

The spend ceiling is ONE number across every trigger kind — chat, direct
invocation, ambient fires, evals — summed from the database (so it is
shared across replicas) over the current UTC day, enforced at `create_run`
behind its own §3.7.1 gate. Past the ceiling a chat is a 429 with
Retry-After, an eval batch stops, and an ambient fire is HELD on the event
with the reason, so nothing spends behind an operator's back.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import obs
from app.db import get_session_factory
from app.llm import pricing
from app.models import Run, RunStep
from app.orchestrator import admission

logger = structlog.get_logger("cost")

RUN_KINDS = ("chat", "direct", "ambient", "eval")
_SPEND_CACHE_S = 5.0
_cache: tuple[float, dict[str, Any]] | None = None


class SpendCeilingReached(admission.AtCapacity):
    """The day's spend is at the ceiling: refuse the run, whatever its kind."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, retry_after_s=3600, status_code=429)


def run_kind(run: Run) -> str:
    if run.is_eval:
        return "eval"
    if run.trigger:
        return "ambient"
    if run.orchestrator_mode == "direct":
        return "direct"
    return "chat"


def run_cost(
    totals: tuple[int, int],
    steps: list[tuple[str | None, int, int]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Price a run from its captured usage. `steps` = (model, in, out)."""
    overrides = (
        settings.get("model_prices") if isinstance(settings.get("model_prices"), dict) else None
    )
    priced_usd = 0.0
    priced_any = False
    unpriced_tokens = 0
    stepped_in = stepped_out = 0
    for model, tin, tout in steps:
        stepped_in += tin
        stepped_out += tout
        if not (tin or tout):
            continue
        usd = pricing.cost_usd(model, tin, tout, overrides) if model else None
        if usd is None:
            unpriced_tokens += tin + tout
        else:
            priced_usd += usd
            priced_any = True
    rest_in = max(totals[0] - stepped_in, 0)
    rest_out = max(totals[1] - stepped_out, 0)
    if rest_in or rest_out:
        ref = str(settings.get("formatter_model") or settings.get("default_model") or "")
        usd = pricing.cost_usd(ref, rest_in, rest_out, overrides) if ref else None
        if usd is None:
            unpriced_tokens += rest_in + rest_out
        else:
            priced_usd += usd
            priced_any = True
    return {
        "cost_usd": round(priced_usd, 6) if priced_any else None,
        "cost_priced": unpriced_tokens == 0 and (priced_any or (totals[0] + totals[1]) == 0),
        "unpriced_tokens": unpriced_tokens,
    }


async def _step_usage(
    session: AsyncSession, run_ids: list[UUID]
) -> dict[UUID, list[tuple[str | None, int, int]]]:
    if not run_ids:
        return {}
    rows = (
        await session.execute(
            select(
                RunStep.run_id,
                RunStep.model,
                func.coalesce(func.sum(RunStep.input_tokens), 0),
                func.coalesce(func.sum(RunStep.output_tokens), 0),
            )
            .where(RunStep.run_id.in_(run_ids))
            .group_by(RunStep.run_id, RunStep.model)
        )
    ).all()
    out: dict[UUID, list[tuple[str | None, int, int]]] = defaultdict(list)
    for run_id, model, tin, tout in rows:
        out[run_id].append((model, int(tin), int(tout)))
    return out


async def attach_costs(
    session: AsyncSession, runs: list[Run], settings: dict[str, Any]
) -> dict[UUID, dict[str, Any]]:
    """One grouped query for a page of runs → {run_id: run_cost(...)}."""
    usage = await _step_usage(session, [r.id for r in runs])
    return {
        r.id: run_cost((r.total_input_tokens, r.total_output_tokens), usage.get(r.id, []), settings)
        for r in runs
    }


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


async def spend_today(
    settings: dict[str, Any], now: datetime | None = None, *, fresh: bool = False
) -> dict[str, Any]:
    """The day's spend across every run kind, from the database (shared by
    every replica), cached briefly — admission checks it on every run."""
    global _cache
    mono = time.monotonic()
    if not fresh and _cache is not None and mono - _cache[0] < _SPEND_CACHE_S:
        return dict(_cache[1])
    now = now or datetime.now(UTC)
    start, end = _day_bounds(now)
    by_kind: dict[str, float] = defaultdict(float)
    total = 0.0
    unpriced = 0
    count = 0
    async with get_session_factory()() as session:
        runs = list(
            (
                await session.execute(
                    select(Run).where(Run.started_at >= start, Run.started_at < end)
                )
            ).scalars()
        )
        usage = await _step_usage(session, [r.id for r in runs])
    for run in runs:
        count += 1
        priced = run_cost(
            (run.total_input_tokens, run.total_output_tokens), usage.get(run.id, []), settings
        )
        if priced["cost_usd"]:
            by_kind[run_kind(run)] += priced["cost_usd"]
            total += priced["cost_usd"]
        unpriced += int(priced["unpriced_tokens"])
    ceiling_on = bool(settings.get("spend_ceiling_enabled"))
    ceiling = float(settings.get("spend_ceiling_usd_per_day") or 0.0)
    result = {
        "day": start.date().isoformat(),
        "usd_today": round(total, 6),
        "runs_today": count,
        "unpriced_tokens": unpriced,
        "by_kind": {k: round(v, 6) for k, v in by_kind.items()},
        "ceiling": {
            "enabled": ceiling_on,
            "usd_per_day": ceiling,
            "remaining": round(max(ceiling - total, 0.0), 6) if ceiling_on else None,
            "reached": bool(ceiling_on and total >= ceiling),
        },
    }
    obs.SPEND_TODAY.set(total)
    _cache = (mono, result)
    return dict(result)


def invalidate_spend_cache() -> None:
    global _cache
    _cache = None


async def refresh_spend_gauge() -> None:
    """Periodic-loop hook: publish `concierge_spend_usd_today` whether or not
    the ceiling gate is on. Without it a fresh process reports $0 until
    something reads /spend — the M53 load drill caught the dashboard saying
    so for a process that had spent real money."""
    from app.orchestrator.graph_mode import load_settings_snapshot

    await spend_today(await load_settings_snapshot(), fresh=True)


async def enforce_spend_ceiling(settings: dict[str, Any], kind: str) -> None:
    """The gate: nothing happens unless `spend_ceiling_enabled` is on."""
    if not settings.get("spend_ceiling_enabled"):
        return
    spend = await spend_today(settings)
    if not spend["ceiling"]["reached"]:
        return
    obs.SPEND_REFUSED.labels(kind=kind).inc()
    ceiling = spend["ceiling"]["usd_per_day"]
    logger.warning(
        "spend_ceiling_refused", kind=kind, usd_today=spend["usd_today"], ceiling=ceiling
    )
    raise SpendCeilingReached(
        f"spend ceiling reached: ${spend['usd_today']:.4f} of ${ceiling:.2f} spent today "
        f"(spend_ceiling_usd_per_day) — runs of every kind are refused until the UTC day "
        f"rolls over or the ceiling is raised in Settings → Cost"
    )
