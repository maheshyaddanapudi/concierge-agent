"""The delivery plane (spec §17.5 — milestone M23): every ambient output is
an outbox row; this module decides WHEN each row reaches the human.

Four tiers: 0 interrupt (budget-debited, quiet-hours-suppressed to
digest-lead), 1 notify (user-returned edge or bounded deferral), 2 digest
(the default — flushed at configured times, on return from long absence,
and led by demoted interrupts), 3 silent (ledger only, delivered at insert).
Feedback becomes a persisted blended reward (§17.7 substrate), and
persistently imprecise categories are demoted one tier through the
append-only policy ledger (§17.6) — the same ledger the M25 learner writes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select

from app.db import get_session_factory
from app.models import AmbientPolicy, Delivery, Run, UserPresence

logger = structlog.get_logger("ambient")

FEEDBACK_VALUES = {"accepted", "dismissed", "ignored"}
PRECISION_WINDOW = 20
PRECISION_MIN_SAMPLE = 5
PRECISION_FLOOR = 0.25
REPETITION_DECAY = 0.8
USEFULNESS_BONUS = 0.5


def in_quiet_hours(now: datetime, ranges: list[str]) -> bool:
    """Quiet hours are absolute (spec §17.5). `ranges` is [start, end] in
    HH:MM; a wrap-around range (22:00→07:00) spans midnight."""
    if len(ranges) != 2:
        return False
    start_h, start_m = (int(x) for x in ranges[0].split(":"))
    end_h, end_m = (int(x) for x in ranges[1].split(":"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if start <= end:
        return start <= now < end
    return now >= start or now < end


async def current_tier_override(category: str) -> int | None:
    """Latest APPLIED policy-ledger row wins (spec §17.6). Queued
    learner_proposal rows are inert until approved (§17.7 propose mode)."""
    async with get_session_factory()() as session:
        row = (
            (
                await session.execute(
                    select(AmbientPolicy)
                    .where(
                        AmbientPolicy.category == category,
                        AmbientPolicy.source != "learner_proposal",
                    )
                    .order_by(AmbientPolicy.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
    return row.tier_override if row is not None else None


async def add_delivery(
    *,
    category: str,
    tier: int,
    urgency: int,
    title: str,
    body: str | None = None,
    run_id: UUID | None = None,
    intent_id: UUID | None = None,
    skey: str | None = None,
    deliver_no_later_than: datetime | None = None,
) -> Delivery:
    """The single insert path: applies the category policy override,
    supersede-collapses pending rows sharing `skey`, and delivers tier-3
    rows immediately (silence is an explicit, logged decision)."""
    override = await current_tier_override(category)
    if override is not None:
        tier = override
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        row = Delivery(
            run_id=run_id,
            intent_id=intent_id,
            category=category,
            tier=tier,
            urgency=urgency,
            title=title[:250],
            body=body,
            skey=skey,
            deliver_no_later_than=deliver_no_later_than,
        )
        if tier == 3:
            row.delivered_at = now
            row.channel = "silent"
        session.add(row)
        await session.flush()
        if skey:
            stale = list(
                (
                    await session.execute(
                        select(Delivery).where(
                            Delivery.skey == skey,
                            Delivery.id != row.id,
                            Delivery.delivered_at.is_(None),
                            Delivery.superseded_by.is_(None),
                        )
                    )
                ).scalars()
            )
            for old in stale:
                old.superseded_by = row.id
        await session.commit()
        await session.refresh(row)
    from app import obs

    obs.AMBIENT_OPS.labels(kind="deliver", status=f"queued_t{tier}").inc()
    return row


async def _pending(session: Any, tier: int) -> list[Delivery]:
    return list(
        (
            await session.execute(
                select(Delivery)
                .where(
                    Delivery.tier == tier,
                    Delivery.delivered_at.is_(None),
                    Delivery.superseded_by.is_(None),
                )
                .order_by(Delivery.urgency.desc(), Delivery.created_at)
            )
        ).scalars()
    )


async def _interrupts_delivered_today(session: Any, now: datetime) -> int:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    Delivery.channel == "interrupt", Delivery.delivered_at >= midnight
                )
            )
        ).scalar_one()
    )


async def _presence_active() -> bool:
    async with get_session_factory()() as session:
        row = await session.get(UserPresence, "default")
    return row is not None and row.state == "active"


async def _digest_due(session: Any, now: datetime, digest_times: list[str]) -> bool:
    """Due when we crossed a configured digest time (today) that no digest
    flush has covered yet — a missed time catches up exactly once."""
    occurrences = []
    for hhmm in digest_times:
        try:
            hh, mm = (int(x) for x in hhmm.split(":"))
        except ValueError:
            continue
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at <= now:
            occurrences.append(at)
    if not occurrences:
        return False
    latest_occurrence = max(occurrences)
    last_flush = (
        await session.execute(
            select(func.max(Delivery.delivered_at)).where(Delivery.channel == "digest")
        )
    ).scalar_one()
    return last_flush is None or last_flush < latest_occurrence


async def _digest_flush(now: datetime) -> int:
    """Deliver every pending tier-2 row as one digest batch, urgency first
    (demoted interrupts lead — they kept urgency 5)."""
    async with get_session_factory()() as session:
        rows = await _pending(session, 2)
        for row in rows:
            row.delivered_at = now
            row.channel = "digest"
        await session.commit()
    if rows:
        from app import obs

        obs.AMBIENT_OPS.labels(kind="digest", status="flushed").inc()
        logger.info("ambient_digest", tier="ambient", kind="digest", items=len(rows))
    return len(rows)


async def _flush_tier1(now: datetime, *, quiet: bool, force: bool = False) -> int:
    """Tier 1: the user-returned edge (or current presence) delivers; the
    bounded deferral (spec §17.5, Horvitz) delivers past the deadline even
    with nobody present."""
    delivered = 0
    present = force or await _presence_active()
    async with get_session_factory()() as session:
        for row in await _pending(session, 1):
            deadline_passed = (
                row.deliver_no_later_than is not None and now >= row.deliver_no_later_than
            )
            if not (present or deadline_passed):
                continue
            if quiet:
                row.tier = 2  # quiet hours absolute — rides the digest
                continue
            row.delivered_at = now
            row.channel = "notify"
            delivered += 1
        await session.commit()
    return delivered


async def flush_deliveries(now: datetime | None = None) -> dict[str, int]:
    """The tick's delivery pass: interrupts (budget + quiet), notifies
    (presence/deferral), and time-based digests."""
    from app.registry_cache import get_cache

    now = now or datetime.now(UTC)
    cache = get_cache()
    quiet_ranges = list(await cache.setting("ambient_quiet_hours") or [])
    budget = int(await cache.setting("ambient_notification_budget_per_day"))
    digest_times = list(await cache.setting("ambient_digest_times") or [])
    quiet = in_quiet_hours(now, quiet_ranges)
    out = {"interrupt": 0, "notify": 0, "digest": 0, "demoted": 0}

    async with get_session_factory()() as session:
        used = await _interrupts_delivered_today(session, now)
        for row in await _pending(session, 0):
            if quiet or used >= budget:
                # digest-lead: demoted but keeps its urgency, so it sorts first
                row.tier = 2
                out["demoted"] += 1
                logger.info(
                    "ambient_interrupt_demoted",
                    tier="ambient",
                    kind="deliver",
                    reason="quiet hours" if quiet else "budget exhausted",
                )
                continue
            row.delivered_at = now
            row.channel = "interrupt"
            used += 1
            out["interrupt"] += 1
        await session.commit()

    out["notify"] = await _flush_tier1(now, quiet=quiet)

    # quiet hours absolute (spec §17.5): even a catch-up digest waits them
    # out — the user-returned flush stays live because the user is present
    if not quiet:
        async with get_session_factory()() as session:
            due = await _digest_due(session, now, digest_times)
        if due:
            out["digest"] = await _digest_flush(now)
    return out


async def on_user_returned(away_s: float, now: datetime | None = None) -> None:
    """The away→active edge (spec §17.5): every return flushes tier 1; a
    return from absence > 1h also flushes the digest as one collapsed
    'while you were away' stack. Micro-absences flush tier 1 only."""
    now = now or datetime.now(UTC)
    await _flush_tier1(now, quiet=False, force=True)
    if away_s > 3600:
        await _digest_flush(now)


# ── feedback → blended reward (spec §17.7 substrate) ─────────────────


async def compute_reward(delivery: Delivery, feedback: str) -> float:
    """acceptance + downstream usefulness − dismissal penalty, with a
    repetition-decay term on the positive part (recovering-bandit shape).
    Pure acceptance optimization is forbidden by construction."""
    base = {"accepted": 1.0, "dismissed": -1.0, "ignored": 0.0}[feedback]
    anchor = delivery.delivered_at or datetime.now(UTC)
    async with get_session_factory()() as session:
        repeats = int(
            (
                await session.execute(
                    select(func.count()).where(
                        Delivery.category == delivery.category,
                        Delivery.id != delivery.id,
                        Delivery.delivered_at.isnot(None),
                        Delivery.delivered_at >= anchor - timedelta(hours=24),
                        Delivery.delivered_at <= anchor,
                    )
                )
            ).scalar_one()
        )
        usefulness = 0.0
        if feedback == "accepted" and delivery.run_id is not None:
            run = await session.get(Run, delivery.run_id)
            if run is not None and delivery.delivered_at is not None:
                later = (
                    await session.execute(
                        select(func.count()).where(
                            Run.conversation_id == run.conversation_id,
                            Run.started_at > delivery.delivered_at,
                            Run.id != run.id,
                        )
                    )
                ).scalar_one()
                if later:
                    usefulness = USEFULNESS_BONUS
    reward = base * (REPETITION_DECAY**repeats) if base > 0 else base
    return round(reward + usefulness, 4)


async def record_feedback(delivery_id: UUID, feedback: str) -> Delivery | None:
    """Capture accepted/dismissed/ignored, persist the blended reward, and
    re-evaluate the category's precision rule."""
    if feedback not in FEEDBACK_VALUES:
        raise ValueError(f"feedback must be one of {sorted(FEEDBACK_VALUES)}")
    async with get_session_factory()() as session:
        row = await session.get(Delivery, delivery_id)
        if row is None:
            return None
        row.feedback = feedback
        row.reward = await compute_reward(row, feedback)
        await session.commit()
        await session.refresh(row)
    from app import obs

    obs.AMBIENT_OPS.labels(kind="deliver", status=f"feedback_{feedback}").inc()
    # the rule is the STATIC policy: once learning is on (auto|propose) the
    # §17.7 learner owns re-tiering — reward-weighted, both directions
    from app.registry_cache import get_cache

    if str(await get_cache().setting("ambient_learning_mode")) == "off":
        await apply_precision_rule(row.category)
    return row


async def category_precision(category: str) -> tuple[float | None, int]:
    """Intervention precision (spec §17.3): accepted / (accepted+dismissed)
    over the last PRECISION_WINDOW judged items."""
    async with get_session_factory()() as session:
        rows = list(
            (
                await session.execute(
                    select(Delivery.feedback)
                    .where(
                        Delivery.category == category,
                        Delivery.feedback.in_(["accepted", "dismissed"]),
                    )
                    .order_by(Delivery.created_at.desc())
                    .limit(PRECISION_WINDOW)
                )
            ).scalars()
        )
    n = len(rows)
    if n == 0:
        return None, 0
    return rows.count("accepted") / n, n


async def apply_precision_rule(category: str) -> AmbientPolicy | None:
    """Rule-based auto-downgrade (spec §17.3/§17.6): persistently low
    precision demotes the category ONE tier (never into 0, never past 3),
    as an append-only, revertible ledger entry."""
    precision, n = await category_precision(category)
    if precision is None or n < PRECISION_MIN_SAMPLE or precision >= PRECISION_FLOOR:
        return None
    override = await current_tier_override(category)
    if override is not None:
        base_tier = override
    else:
        async with get_session_factory()() as session:
            latest = (
                (
                    await session.execute(
                        select(Delivery.tier)
                        .where(Delivery.category == category)
                        .order_by(Delivery.created_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
        base_tier = int(latest) if latest is not None else 2
    target = min(base_tier + 1, 3)
    if target == base_tier:
        return None
    async with get_session_factory()() as session:
        policy = AmbientPolicy(
            category=category,
            tier_override=target,
            reason=(
                f"intervention precision {precision:.2f} over {n} judged items — "
                f"demoted tier {base_tier}→{target}"
            ),
            source="rule",
        )
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
    from app import obs

    obs.AMBIENT_OPS.labels(kind="deliver", status="auto_downgraded").inc()
    logger.info(
        "ambient_category_downgraded",
        tier="ambient",
        kind="deliver",
        category=category,
        new_tier=target,
    )
    return policy
