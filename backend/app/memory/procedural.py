"""L3 procedural learning (spec §16.5).

Consumes the episodic layer; lands in existing governance. The
experience-following caution (research 03 §5) applies throughout: only
positively-signaled runs are harvested, exemplars carry an ExpeL vote
lifecycle (upvote on reuse-success, downvote on reuse-failure, retire at
zero), and mined skill proposals pass doclint + the overlap judge and land
INACTIVE for human review — no autonomous registry mutation.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy import text as sql_text

from app.db import get_session_factory
from app.models import PlanExemplar, RoutingStat, Run, RunStep

logger = structlog.get_logger("memory")

_EXEMPLAR_LEG_LIMIT = 15
_RRF_K = 60
_MIN_CLUSTER = 3  # fallback-mining threshold: recurring means ≥ this many runs
PROPOSAL_PREFIX = "[proposed from fallback mining] "


def _or_q(task: str) -> str:
    from app.memory.rank import or_tsquery

    return or_tsquery(task)


async def _enabled() -> bool:
    from app.registry_cache import get_cache

    cache = get_cache()
    return bool(await cache.setting("memory_enabled")) and bool(
        await cache.setting("procedural_learning_enabled")
    )


# ── routing stats ─────────────────────────────────────────────────────


async def update_routing_stats(run_id: UUID) -> None:
    """Fold one finished run's route steps into per-capability stats."""
    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None or run.status not in {"completed", "failed"}:
            return
        steps = list(
            (
                await session.execute(
                    select(RunStep).where(RunStep.run_id == run_id, RunStep.step_type == "route")
                )
            ).scalars()
        )
        hitl_denied = bool(
            (
                await session.execute(
                    select(RunStep).where(
                        RunStep.run_id == run_id,
                        RunStep.step_type == "hitl",
                    )
                )
            )
            .scalars()
            .all()
            and any(
                (s.output or {}).get("status") == "denied"
                for s in (
                    await session.execute(
                        select(RunStep).where(RunStep.run_id == run_id, RunStep.step_type == "hitl")
                    )
                ).scalars()
            )
        )
        duration_ms = 0.0
        if run.finished_at and run.started_at:
            duration_ms = (run.finished_at - run.started_at).total_seconds() * 1000
        for step in steps:
            out = step.output or {}
            rung = out.get("rung")
            if not rung:
                continue
            resolved = out.get("resolved_to") or {}
            entity_id = resolved.get("entity_id")
            entity_name = resolved.get("entity_name")
            key = f"{rung}:{entity_id or entity_name or '-'}"[:320]
            stat = await session.get(RoutingStat, key)
            if stat is None:
                stat = RoutingStat(
                    capability_key=key,
                    rung=str(rung),
                    entity_id=UUID(entity_id) if entity_id else None,
                    entity_name=entity_name,
                    runs_total=0,
                    runs_completed=0,
                    runs_failed=0,
                    hitl_denied=0,
                    mean_input_tokens=0.0,
                    mean_output_tokens=0.0,
                    mean_duration_ms=0.0,
                )
                session.add(stat)
            n = stat.runs_total
            stat.runs_total = n + 1
            if run.status == "completed":
                stat.runs_completed += 1
            else:
                stat.runs_failed += 1
            if hitl_denied:
                stat.hitl_denied += 1
            stat.mean_input_tokens = (stat.mean_input_tokens * n + run.total_input_tokens) / (n + 1)
            stat.mean_output_tokens = (stat.mean_output_tokens * n + run.total_output_tokens) / (
                n + 1
            )
            stat.mean_duration_ms = (stat.mean_duration_ms * n + duration_ms) / (n + 1)
            stat.last_used_at = datetime.now(UTC)
        await session.commit()


# ── plan exemplars: harvest + vote lifecycle ──────────────────────────


def _positive_signal(run: Run, steps: list[RunStep]) -> bool:
    if run.status != "completed":
        return False
    denied = any(
        s.step_type == "hitl" and (s.output or {}).get("status") == "denied" for s in steps
    )
    return not denied


async def harvest_exemplar(run_id: UUID) -> PlanExemplar | None:
    """Store a positively-signaled run's routing shape, keyed by task text.
    M51 (arch-H15): the embedding is computed between the read and the
    write session, never inside one."""
    from app.memory.store import _embed_text, _store_embedding

    async with get_session_factory()() as session:
        run = await session.get(Run, run_id)
        if run is None or run.orchestrator_mode not in {"graph", "agentic"}:
            return None
        steps = list(
            (await session.execute(select(RunStep).where(RunStep.run_id == run_id))).scalars()
        )
        if not _positive_signal(run, steps):
            return None
        routes = [
            {
                "rung": (s.output or {}).get("rung"),
                "entity": ((s.output or {}).get("resolved_to") or {}).get("entity_name"),
            }
            for s in steps
            if s.step_type == "route" and (s.output or {}).get("rung")
        ]
        if not routes and not (run.plan or {}).get("entries"):
            return None  # nothing procedural to learn (direct answers etc.)
        existing = (
            await session.execute(select(PlanExemplar).where(PlanExemplar.run_id == run_id))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        trace: dict[str, Any] = {"routes": routes}
        if run.orchestrator_mode == "graph" and run.plan:
            trace["plan_entries"] = (run.plan or {}).get("entries", [])
        task_text = " ".join((run.chat_message or "").split())[:1000]
        mode = run.orchestrator_mode
    embedded = await _embed_text(task_text)
    async with get_session_factory()() as session:
        existing = (
            await session.execute(select(PlanExemplar).where(PlanExemplar.run_id == run_id))
        ).scalar_one_or_none()
        if existing is not None:  # harvested concurrently meanwhile
            return existing
        # born PENDING (review round 2): "completed, no deny" is the model's
        # own word that it finished — the exemplar serves the planner only
        # once the human's next turn (or a quiet conversation) confirms it,
        # the same deferral the reuse vote gets
        exemplar = PlanExemplar(
            run_id=run_id,
            task_text=task_text,
            mode=mode,
            trace=trace,
            votes=1,
            status="pending",
        )
        session.add(exemplar)
        await session.flush()
        await _store_embedding(session, exemplar.id, "plan_exemplars", embedded)
        run_row = await session.get(Run, run_id)
        if run_row is not None:
            pending = dict((run_row.snapshot or {}).get("exemplar_vote") or {})
            if pending.get("status") != "pending":
                pending = {"ids": [], "status": "pending", "at": datetime.now(UTC).isoformat()}
            pending["harvested"] = [str(exemplar.id)]
            run_row.snapshot = {**(run_row.snapshot or {}), "exemplar_vote": pending}
        await session.commit()
        await session.refresh(exemplar)
    logger.info(
        "memory_exemplar_harvest",
        tier="memory",
        kind="harvest",
        run_id=str(run_id),
        routes=len(routes),
    )
    return exemplar


async def vote_exemplars(exemplar_ids: list[UUID], *, success: bool, retire: bool = True) -> None:
    """ExpeL lifecycle: reuse outcome adjusts votes; zero retires — unless
    the vote came from the correction heuristic (`retire=False`): a
    heuristic never retires on its own, only a hard signal (a failed run,
    a denied gate) can take an exemplar to zero (review round 2)."""
    if not exemplar_ids:
        return
    async with get_session_factory()() as session:
        delta = 1 if success else -1
        floor = 0 if retire else 1
        await session.execute(
            update(PlanExemplar)
            .where(PlanExemplar.id.in_(exemplar_ids), PlanExemplar.votes + delta >= floor)
            .values(votes=PlanExemplar.votes + delta)
        )
        await session.execute(
            update(PlanExemplar)
            .where(PlanExemplar.id.in_(exemplar_ids), PlanExemplar.votes <= 0)
            .values(status="retired")
        )
        await session.commit()
    logger.info(
        "memory_exemplar_vote",
        tier="memory",
        kind="harvest",
        count=len(exemplar_ids),
        success=success,
    )


async def settle_harvested(exemplar_ids: list[UUID], *, confirmed: bool) -> None:
    """A pending (just-harvested) exemplar becomes active on confirmation
    and retired on a correction — it never served the planner in between."""
    if not exemplar_ids:
        return
    async with get_session_factory()() as session:
        await session.execute(
            update(PlanExemplar)
            .where(PlanExemplar.id.in_(exemplar_ids), PlanExemplar.status == "pending")
            .values(status="active" if confirmed else "retired")
        )
        await session.commit()


async def _settle(pending: dict[str, Any], *, corrected: bool) -> None:
    """Apply one settled vote: the reused exemplars and the harvested one."""
    ids = [UUID(i) for i in pending.get("ids", [])]
    harvested = [UUID(i) for i in pending.get("harvested", [])]
    if ids:
        # a heuristic downvote never retires (review round 2)
        await vote_exemplars(ids, success=not corrected, retire=not corrected)
    await settle_harvested(harvested, confirmed=not corrected)


async def recall_exemplars(task: str, *, k: int = 2) -> list[PlanExemplar]:
    """Hybrid recall over active exemplars (same RRF shape as memories)."""
    from app.memory.store import active_model_key
    from app.retrieval import _query_vector

    task = " ".join(task.split())
    if not task:
        return []
    async with get_session_factory()() as session:
        lex_ids = [
            r[0]
            for r in (
                await session.execute(
                    sql_text(
                        """
                        SELECT e.id FROM plan_exemplars e,
                               to_tsquery('english', :q) tsq
                        WHERE e.fts @@ tsq AND e.status = 'active'
                        ORDER BY ts_rank_cd(e.fts, tsq) DESC
                        LIMIT :n
                        """
                    ),
                    {"q": _or_q(task), "n": _EXEMPLAR_LEG_LIMIT},
                )
            ).all()
        ]
        vec_ids: list[UUID] = []
        qvec = await _query_vector(task)
        model_key = await active_model_key() if qvec is not None else None
        from app.memory.dims import vector_column

        typed = vector_column(model_key) if model_key else None  # M54: the typed column
        if qvec is not None and model_key is not None and typed is not None:
            col, vtype = typed
            vec_ids = [
                r[0]
                for r in (
                    await session.execute(
                        sql_text(
                            f"""
                            SELECT e.id FROM plan_exemplars e
                            JOIN memory_embeddings emb
                              ON emb.ref_id = e.id AND emb.table_ref = 'plan_exemplars'
                             AND emb.model_key = :model_key
                            WHERE e.status = 'active'
                            ORDER BY emb.{col} <=> CAST(:qvec AS {vtype})
                            LIMIT :n
                            """  # noqa: S608 — column and type are code constants; values are bound
                        ),
                        {
                            "q": _or_q(task),
                            "n": _EXEMPLAR_LEG_LIMIT,
                            "qvec": str(list(qvec)),
                            "model_key": model_key,
                        },
                    )
                ).all()
            ]
        rrf: dict[UUID, float] = {}
        for ranking in ([lex_ids] if lex_ids else []) + ([vec_ids] if vec_ids else []):
            for i, eid in enumerate(ranking):
                rrf[eid] = rrf.get(eid, 0.0) + 1.0 / (_RRF_K + i + 1)
        if not rrf:
            return []
        ordered = sorted(rrf, key=lambda eid: rrf[eid], reverse=True)[:k]
        rows = {
            e.id: e
            for e in (
                await session.execute(select(PlanExemplar).where(PlanExemplar.id.in_(ordered)))
            ).scalars()
        }
    return [rows[eid] for eid in ordered if eid in rows]


async def exemplar_block(task: str) -> tuple[str, list[UUID]]:
    """The planner's budgeted few-shot block (spec §16.5), or ("", [])."""
    if not await _enabled():
        return "", []
    try:
        exemplars = await recall_exemplars(task, k=2)
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("memory_exemplar_recall_failed", error=str(exc))
        return "", []
    if not exemplars:
        return "", []
    lines = []
    for e in exemplars:
        routes = " → ".join(
            f"{r.get('rung')}({r.get('entity')})" for r in (e.trace or {}).get("routes", [])
        )
        lines.append(f'- past ask: "{e.task_text[:160]}" → what worked: {routes or "direct plan"}')
    block = (
        "\nSimilar past asks and the routing that worked (guidance, not law):\n"
        + "\n".join(lines)
        + "\n"
    )
    ids = [e.id for e in exemplars]
    logger.info(
        "memory_exemplar_inject", tier="memory", kind="inject", surface="planner", count=len(ids)
    )
    return block, ids


async def post_run_procedural(run_id: UUID) -> None:
    """Scheduler chain entry: stats + exemplar harvest + reuse voting."""
    if not await _enabled():
        return
    await update_routing_stats(run_id)
    await harvest_exemplar(run_id)
    # vote on exemplars this run REUSED (recorded on the run context at inject)
    from app.orchestrator.context import get_run_context

    ctx = get_run_context()
    used: list[UUID] = list(getattr(ctx, "used_exemplar_ids", []) or []) if ctx else []
    if used:
        async with get_session_factory()() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            if run.status != "completed":
                await vote_exemplars(used, success=False)
                return
            # spec §16.5: a positive vote needs "completed, no deny, AND no
            # immediate correction". The first two are known now; the third
            # is not — "the model said it finished" is the same model that
            # planned, so the vote is DEFERRED: settled when the next turn
            # in the conversation is not a correction, or by the sweep once
            # the conversation has stayed quiet (hardening wave)
            pending = dict((run.snapshot or {}).get("exemplar_vote") or {})
            if pending.get("status") != "pending":
                pending = {"status": "pending", "at": datetime.now(UTC).isoformat()}
            pending["ids"] = [str(u) for u in used]
            run.snapshot = {**(run.snapshot or {}), "exemplar_vote": pending}
            await session.commit()


# an opening that reads as a correction of the previous answer — matched
# at the START of the next turn only (review round 2: a bare "actually" or
# "wrong" anywhere in the first 80 characters caught "nothing wrong with
# that, thanks!"), so the heuristic errs toward NO vote rather than a
# false downvote
_CORRECTION_OPENERS = (
    "no,",
    "no.",
    "no ",
    "nope",
    "not what",
    "that's wrong",
    "that is wrong",
    "that's not right",
    "that is not right",
    "that doesn't look right",
    "that does not look right",
    "wrong",
    "wrong,",
    "i meant",
    "try again",
    "redo",
    "do it again",
    "incorrect",
    "not correct",
    "didn't ask",
    "did not ask",
    "are you sure",
    "hmm, are you sure",
    "still wrong",
    "that's incorrect",
)


def looks_like_correction(previous_ask: str, next_ask: str) -> bool:
    """Deterministic 'immediate correction' heuristic: the next turn OPENS
    with a correction, or re-asks the same thing (high token overlap with
    the previous ask). Deliberately conservative — a miss costs one
    unearned upvote, a false hit costs a downvote."""
    text = " ".join(next_ask.strip().lower().split())
    if any(text.startswith(m) for m in _CORRECTION_OPENERS):
        return True
    prev = {t for t in previous_ask.lower().split() if len(t) > 3}
    nxt = {t for t in text.split() if len(t) > 3}
    if len(prev) >= 4 and len(nxt) >= 4:
        return len(prev & nxt) / len(prev) >= 0.6
    return False


async def judge_pending_vote(conversation_id: UUID, next_message: str) -> str | None:
    """The next turn in a conversation settles EVERY pending exemplar vote
    in it: the newest pending run against the new message (a correction
    downvotes, anything else upvotes); older pending runs — a run that was
    still executing when the next turn arrived, a direct invocation, a
    retry sitting after it — were followed by turns that were not judged
    corrections of them and are confirmed (review round 2: only the newest
    run used to be looked at, so those stayed pending forever). Returns the
    newest decision, or None when nothing was pending."""
    if not await _enabled():
        return None
    settled: list[tuple[dict[str, Any], bool, UUID]] = []
    async with get_session_factory()() as session:
        runs = list(
            (
                await session.execute(
                    select(Run)
                    .where(
                        Run.conversation_id == conversation_id,
                        Run.snapshot.isnot(None),
                        Run.snapshot["exemplar_vote"]["status"].astext == "pending",
                    )
                    .order_by(Run.started_at.desc())
                )
            ).scalars()
        )
        for i, run in enumerate(runs):
            pending = dict((run.snapshot or {}).get("exemplar_vote") or {})
            corrected = i == 0 and looks_like_correction(run.chat_message, next_message)
            decision = "corrected" if corrected else "confirmed"
            run.snapshot = {
                **(run.snapshot or {}),
                "exemplar_vote": {**pending, "status": decision, "settled_by": "next_turn"},
            }
            settled.append((pending, corrected, run.id))
        await session.commit()
    if not settled:
        return None
    for pending, corrected, run_id in settled:
        await _settle(pending, corrected=corrected)
        logger.info(
            "memory_exemplar_vote_settled",
            run_id=str(run_id),
            decision="corrected" if corrected else "confirmed",
        )
    return "corrected" if settled[0][1] else "confirmed"


QUIET_SETTLE_S = 600


async def settle_exemplar_votes(now: datetime | None = None) -> int:
    """The sweep half of the deferred vote: a completed run whose
    conversation has stayed quiet for QUIET_SETTLE_S with no later run is
    taken as not corrected and its exemplars upvoted. Returns the number
    of runs settled."""
    if not await _enabled():
        return 0
    now = now or datetime.now(UTC)
    settled = 0
    async with get_session_factory()() as session:
        rows = list(
            (
                await session.execute(
                    select(Run).where(
                        Run.status == "completed",
                        Run.snapshot.isnot(None),
                        Run.snapshot["exemplar_vote"]["status"].astext == "pending",
                    )
                )
            ).scalars()
        )
        to_settle: list[dict[str, Any]] = []
        for run in rows:
            pending = dict((run.snapshot or {}).get("exemplar_vote") or {})
            try:
                at = datetime.fromisoformat(str(pending.get("at")))
            except ValueError:
                at = run.finished_at or run.started_at
            if at is None or (now - at).total_seconds() < QUIET_SETTLE_S:
                continue
            later = (
                await session.execute(
                    select(Run.chat_message)
                    .where(
                        Run.conversation_id == run.conversation_id,
                        Run.started_at > run.started_at,
                    )
                    .order_by(Run.started_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            # a later turn that the next-turn path did not settle (it was
            # in flight, or not a chat) is judged here against that turn;
            # no later turn at all is a quiet conversation — confirmed
            corrected = later is not None and looks_like_correction(run.chat_message, later)
            run.snapshot = {
                **(run.snapshot or {}),
                "exemplar_vote": {
                    **pending,
                    "status": "corrected" if corrected else "confirmed",
                    "settled_by": "later_turn" if later is not None else "quiet",
                },
            }
            to_settle.append({**pending, "_corrected": corrected})
        await session.commit()
    for pending in to_settle:
        await _settle(pending, corrected=bool(pending.pop("_corrected")))
        settled += 1
    if settled:
        logger.info("memory_exemplar_votes_settled", count=settled)
    return settled


# ── fallback mining → skill proposals ─────────────────────────────────


def proposal_lint(name: str, description: str, instructions: str) -> list[str]:
    """The document rules doclint applies to a `.skill.md`, on a proposal
    built in memory: a name in the skill-file charset, prose in the
    description, instructions that are not empty. A proposal that would
    fail the seed gate must not reach the review queue either."""
    import re

    problems: list[str] = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", name):
        problems.append(f"name {name!r} is not a skill-file name (lowercase, digits, hyphens)")
    if len(description.strip()) < 20:
        problems.append("description is too short to route by")
    if len(instructions.strip()) < 20:
        problems.append("instructions are too short to execute")
    return problems


async def mine_fallback_skills() -> list[str]:
    """Cluster fallback runs' digests; a recurring cluster drafts an INACTIVE
    dynamic-skill proposal binding exactly the tools those runs actually used
    (spec §16.5). Returns the names of proposals created."""
    if not await _enabled():
        return []
    from app.models import Skill, Tool

    async with get_session_factory()() as session:
        digests = list(
            (
                await session.execute(
                    sql_text(
                        """
                        SELECT d.id, d.run_id, d.text FROM run_digests d
                        WHERE jsonb_exists(d.signals->'rungs', 'fallback')
                        ORDER BY d.created_at DESC LIMIT 200
                        """
                    )
                )
            ).all()
        )
        if len(digests) < _MIN_CLUSTER:
            return []

        # greedy lexical clustering over digest token sets (deterministic)
        def tokens(text: str) -> set[str]:
            return {t for t in text.lower().split() if len(t) > 3}

        clusters: list[list[tuple[Any, Any, str]]] = []
        for row in digests:
            placed = False
            for cluster in clusters:
                seed_tokens = tokens(cluster[0][2])
                overlap = len(tokens(row[2]) & seed_tokens) / max(len(seed_tokens), 1)
                if overlap >= 0.4:
                    cluster.append(tuple(row))
                    placed = True
                    break
            if not placed:
                clusters.append([tuple(row)])
        # drafts are collected with the session open and judged with it
        # CLOSED (arch-H15 / M51: no pool connection held across an LLM
        # call — review round 2)
        drafts: list[dict[str, Any]] = []
        for cluster in clusters:
            if len(cluster) < _MIN_CLUSTER:
                continue
            tool_keys: set[str] = set()
            for c in cluster:
                step_tools = (
                    await session.execute(
                        sql_text(
                            """
                            SELECT DISTINCT rs.node_id FROM run_steps rs
                            WHERE rs.run_id = :rid AND rs.step_type = 'tool_call'
                            """
                        ),
                        {"rid": c[1]},
                    )
                ).all()
                tool_keys.update(t[0] for t in step_tools if t[0])
            bound_ids = [
                t.id
                for t in (
                    await session.execute(select(Tool).where(Tool.tool_key.in_(tool_keys)))
                ).scalars()
            ]
            if not bound_ids:
                continue
            name = f"mined-{abs(hash(cluster[0][2])) % 10_000:04d}"
            exists = (
                await session.execute(select(Skill).where(Skill.name == name))
            ).scalar_one_or_none()
            if exists is not None:
                continue
            summary = cluster[0][2][:160]
            drafts.append(
                {
                    "name": name,
                    "description": PROPOSAL_PREFIX + f"covers a recurring uncovered ask: {summary}",
                    "persona": (
                        "You handle a recurring request the registry did not cover. "
                        "Follow the task precisely and use only your bound tools."
                    ),
                    "instructions": (
                        f"Recurring ask cluster ({len(cluster)} fallback runs). "
                        f"Representative: {summary}"
                    ),
                    "tool_ids": bound_ids,
                    "tool_keys": sorted(tool_keys),
                }
            )
    proposals: list[str] = []
    accepted: list[dict[str, Any]] = []
    from app.overlap import check_skill_overlap

    for draft in drafts:
        # spec §16.5: a MACHINE-authored proposal goes through the same
        # gates a human's save does — doclint's document rules and the §4
        # overlap judge (under its own model role) — before it can reach
        # the review queue; the one path that used to bypass both
        problems = proposal_lint(draft["name"], draft["description"], draft["instructions"])
        if problems:
            logger.info("memory_skill_proposal_rejected", name=draft["name"], problems=problems)
            continue
        verdict = await check_skill_overlap(
            name=draft["name"],
            description=draft["description"],
            instructions=draft["instructions"],
            tool_keys=draft["tool_keys"],
            exclude_id=None,
        )
        if not verdict.judge_available:
            # fail-open is right for a human's save (§4 advisory); for the
            # machine path an unavailable judge is no gate at all — the
            # cluster waits for the next pass (review round 2)
            logger.warning(
                "memory_skill_proposal_deferred", name=draft["name"], reason=verdict.reasoning
            )
            continue
        if verdict.overlap:
            logger.info(
                "memory_skill_proposal_overlaps",
                name=draft["name"],
                match=verdict.match_name,
                overlap_percent=verdict.overlap_percent,
            )
            continue
        logger.info(
            "memory_skill_proposal_judged",
            name=draft["name"],
            overlap_percent=verdict.overlap_percent,
            reasoning=verdict.reasoning[:200],
        )
        accepted.append(draft)
    if accepted:
        from app.api.skills import stamp_skill

        async with get_session_factory()() as session:
            for draft in accepted:
                bound = list(
                    (
                        await session.execute(select(Tool).where(Tool.id.in_(draft["tool_ids"])))
                    ).scalars()
                )
                skill = Skill(
                    name=draft["name"],
                    description=draft["description"],
                    persona=draft["persona"],
                    instructions=draft["instructions"],
                    kind="custom",
                    source="dynamic",
                    status="inactive",  # human review activates (spec §16.5)
                    direct_exposure=False,
                    origin="mined",  # the activation guard keys off this, not the prefix
                    tools=bound,
                )
                stamp_skill(skill, bound)
                # judged at this definition: the audit need not re-read it
                # (the verdict lives on the log, never in the prompt the
                # skill executes with — review round 2)
                skill.overlap_audited_hash = skill.definition_hash
                session.add(skill)
                proposals.append(draft["name"])
            await session.commit()
    if proposals:
        from app.registry_cache import get_cache

        await get_cache().invalidate("skills")
        logger.info("memory_skill_proposals", tier="memory", kind="harvest", proposals=proposals)
    return proposals
