"""Ambient delivery/watch/ledger API (spec §17.5/§17.6 + §8.9 — M23).

Inbox = the deliveries outbox; feedback capture computes and persists the
blended reward. Watches list standing intents with their compiled rules and
cadence state. Ledger exposes the fire/hold audit with per-category
intervention precision.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import AmbientEvent, AmbientPolicy, Delivery, StandingIntent

deliveries_router = APIRouter(prefix="/deliveries", tags=["ambient"])
watches_router = APIRouter(prefix="/watches", tags=["ambient"])
ledger_router = APIRouter(prefix="/ambient", tags=["ambient"])


def _delivery_out(d: Delivery) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "run_id": str(d.run_id) if d.run_id else None,
        "intent_id": str(d.intent_id) if d.intent_id else None,
        "category": d.category,
        "tier": d.tier,
        "urgency": d.urgency,
        "title": d.title,
        "body": d.body,
        "channel": d.channel,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "deliver_no_later_than": (
            d.deliver_no_later_than.isoformat() if d.deliver_no_later_than else None
        ),
        "superseded_by": str(d.superseded_by) if d.superseded_by else None,
        "feedback": d.feedback,
        "reward": d.reward,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@deliveries_router.get("")
async def list_deliveries(
    session: SessionDep, status: str = "all", limit: int = 100
) -> dict[str, Any]:
    query = select(Delivery).order_by(Delivery.created_at.desc()).limit(min(limit, 500))
    if status == "pending":
        query = query.where(Delivery.delivered_at.is_(None), Delivery.superseded_by.is_(None))
    elif status == "delivered":
        query = query.where(Delivery.delivered_at.isnot(None))
    rows = list((await session.execute(query)).scalars())
    return {"items": [_delivery_out(d) for d in rows]}


@deliveries_router.get("/digest-preview")
async def digest_preview(session: SessionDep) -> dict[str, Any]:
    """What the next digest flush would contain, in flush order."""
    rows = list(
        (
            await session.execute(
                select(Delivery)
                .where(
                    Delivery.tier == 2,
                    Delivery.delivered_at.is_(None),
                    Delivery.superseded_by.is_(None),
                )
                .order_by(Delivery.urgency.desc(), Delivery.created_at)
            )
        ).scalars()
    )
    return {"items": [_delivery_out(d) for d in rows]}


class FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str


@deliveries_router.post("/{delivery_id}/feedback")
async def give_feedback(delivery_id: UUID, body: FeedbackBody) -> dict[str, Any]:
    from app.ambient.deliver import FEEDBACK_VALUES, record_feedback

    if body.feedback not in FEEDBACK_VALUES:
        raise HTTPException(422, f"feedback must be one of {sorted(FEEDBACK_VALUES)}")
    row = await record_feedback(delivery_id, body.feedback)
    if row is None:
        raise HTTPException(404, "no such delivery")
    return _delivery_out(row)


def _watch_out(w: StandingIntent) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "text": w.text,
        "condition_type": w.condition_type,
        "compiled": w.compiled,
        "semantic_predicate": w.semantic_predicate,
        "judge_model_ref": w.judge_model_ref,
        "watermark": w.watermark,
        "cadence": {
            "base_interval_s": w.base_interval_s,
            "current_interval_s": w.current_interval_s,
            "max_interval_s": w.max_interval_s,
            "consecutive_quiet": w.consecutive_quiet,
            "last_checked_at": w.last_checked_at.isoformat() if w.last_checked_at else None,
        },
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "delivery": w.delivery,
        "status": w.status,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@watches_router.get("")
async def list_watches(session: SessionDep, limit: int = 100) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(StandingIntent)
                .order_by(StandingIntent.created_at.desc())
                .limit(min(limit, 500))
            )
        ).scalars()
    )
    return {"items": [_watch_out(w) for w in rows]}


class WatchPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


@watches_router.patch("/{intent_id}")
async def patch_watch(intent_id: UUID, body: WatchPatch, session: SessionDep) -> dict[str, Any]:
    if body.status not in {"active", "paused", "retired"}:
        raise HTTPException(422, "status must be active | paused | retired")
    row = await session.get(StandingIntent, intent_id)
    if row is None:
        raise HTTPException(404, "no such watch")
    if row.status == "proposed" and body.status == "active":
        pass  # confirming a proposal from the UI is allowed
    row.status = body.status
    await session.commit()
    await session.refresh(row)
    return _watch_out(row)


@ledger_router.get("/ledger")
async def ledger(session: SessionDep, limit: int = 100, verdict: str = "all") -> dict[str, Any]:
    query = select(AmbientEvent).order_by(AmbientEvent.received_at.desc()).limit(min(limit, 500))
    if verdict in {"fired", "held", "dropped", "expired"}:
        query = query.where(AmbientEvent.verdict == verdict)
    elif verdict == "pending":
        query = query.where(AmbientEvent.verdict.is_(None))
    rows = list((await session.execute(query)).scalars())
    return {
        "items": [
            {
                "id": str(e.id),
                "kind": e.kind,
                "source": e.source,
                "routine_id": str(e.routine_id) if e.routine_id else None,
                "intent_id": str(e.intent_id) if e.intent_id else None,
                "verdict": e.verdict,
                "verdict_reason": e.verdict_reason,
                "decision": e.decision,
                "causation_id": str(e.causation_id) if e.causation_id else None,
                "correlation_id": str(e.correlation_id) if e.correlation_id else None,
                "depth": e.depth,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
            }
            for e in rows
        ]
    }


@ledger_router.get("/precision")
async def precision(session: SessionDep) -> dict[str, Any]:
    """Per-category intervention precision + the active policy override."""
    from app.ambient.deliver import category_precision

    categories = list((await session.execute(select(Delivery.category).distinct())).scalars())
    policies: dict[str, AmbientPolicy] = {}
    for p in (
        (
            await session.execute(
                select(AmbientPolicy)
                .where(AmbientPolicy.source != "learner_proposal")  # inert until approved
                .order_by(AmbientPolicy.created_at)
            )
        )
        .scalars()
        .all()
    ):
        policies[p.category] = p  # latest applied wins
    out = []
    for cat in sorted(categories):
        prec, n = await category_precision(cat)
        policy = policies.get(cat)
        out.append(
            {
                "category": cat,
                "precision": prec,
                "judged": n,
                "tier_override": policy.tier_override if policy else None,
                "override_reason": policy.reason if policy else None,
                "override_source": policy.source if policy else None,
            }
        )
    return {"items": out}


@ledger_router.get("/policies")
async def policies(session: SessionDep, limit: int = 100) -> dict[str, Any]:
    """The append-only policy ledger, newest first (§17.6 audit + revert)."""
    rows = list(
        (
            await session.execute(
                select(AmbientPolicy)
                .order_by(AmbientPolicy.created_at.desc())
                .limit(min(limit, 500))
            )
        ).scalars()
    )
    return {
        "items": [
            {
                "id": str(p.id),
                "category": p.category,
                "tier_override": p.tier_override,
                "reason": p.reason,
                "source": p.source,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ]
    }


class PolicyRevertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str


@ledger_router.post("/policies/{policy_id}/approve")
async def approve_policy(policy_id: UUID) -> dict[str, Any]:
    """Approve a queued learner proposal (spec §17.7 propose mode)."""
    from app.ambient.learn import approve_proposal

    row = await approve_proposal(policy_id)
    if row is None:
        raise HTTPException(404, "no learner proposal with that id")
    return {
        "id": str(row.id),
        "category": row.category,
        "tier_override": row.tier_override,
        "status": "applied",
    }


@ledger_router.post("/policies/revert")
async def revert_policy(body: PolicyRevertBody, session: SessionDep) -> dict[str, Any]:
    """One-click revert (spec §17.7): append a clearing row for the
    category — history stays, the override stops applying."""
    row = AmbientPolicy(
        category=body.category,
        tier_override=None,
        reason="reverted by user",
        source="user",
    )
    session.add(row)
    await session.commit()
    return {"category": body.category, "tier_override": None, "status": "reverted"}
