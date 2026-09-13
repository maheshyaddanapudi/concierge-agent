"""Memory retrieval (spec §16.3).

Hybrid candidates in SQL (lexical GIN + pgvector cosine over the active
model_key), composite scoring in Python over the fused candidate set:

    score = (w_rel·relevance + w_rec·recency + w_imp·importance/10) / Σw

- relevance: the blend of the two legs' ABSOLUTE match scores — cosine
  similarity from the vector leg, query coverage (`ts_rank_cd` over the
  doc ÷ `ts_rank_cd` over the query's own tsvector) from the lexical one.
  Reciprocal-rank fusion still fuses the two candidate sets and breaks
  score ties, but it never *scores*: RRF is rank-normalized, so its top
  hit is 1.0 however bad the match — the same reasoning `store.py` records
  for the dedup gate ("the RRF relevance is rank-normalized … so it must
  never gate"). With rank-normalized relevance no query could ever return
  empty over a non-empty store, because the vector leg carries no distance
  predicate and so returns rows for literally any query.
- recency:   exp(−ln2 · hours_since_last_ACCESS / half_life) — rehearsal
  refreshes memories (Generative Agents; research 03 §2)
- importance: the write-time 1–10 score

Score floor: below it nothing is returned — an empty block beats a
distracting one (research 03 §6). The floor gates the composite AND the
absolute relevance, because recency+importance alone carry
(W_REC + W_IMP/2)/ΣW ≈ 0.46 of the composite for any fresh row: a row that
is not ABOUT the query has to be refused on relevance itself or recall can
never abstain. Pinned rows bypass the floor (they are the always-injected
profile, spec §16.3). `as_of` switches to bi-temporal point-in-time
predicates. No embedding model ⇒ lexical-only, silently.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import bindparam, select, update
from sqlalchemy import text as sql_text

from app.db import get_session_factory
from app.models import Memory

logger = structlog.get_logger("memory")

_RRF_K = 60
_CANDIDATES_PER_LEG = 40
W_REL, W_REC, W_IMP = 1.0, 0.8, 0.6
# the two legs' weights inside `relevance`. A row only one leg returned
# keeps only that leg's weight — agreement IS evidence, and the damping is
# what lets the floor refuse a row the vector leg dragged back for a query
# it shares nothing with. Lexical leads because coverage is calibrated and
# query-anchored: it is exactly 0 on a non-match, where cosine has no zero
# and no cross-model calibration. When no embedding model is configured the
# vector leg never runs and the lexical score stands alone undamped (§7.4
# degradation, not a penalty).
W_ABS_VEC, W_ABS_LEX = 0.4, 0.6
DEFAULT_HALF_LIFE_HOURS = 30.0 * 24


def _auth_uid() -> Any:
    from app.auth import current_user_id

    return current_user_id()


@dataclass
class RecallHit:
    memory: Memory
    score: float
    relevance: float
    recency: float
    importance: float
    linked: bool = False  # §16.7: reached via an entity hop, not similarity


def _temporal_predicate(as_of: datetime | None) -> str:
    if as_of is None:
        return "m.status = 'active'"
    # what was believed at T about facts valid at T (research 04 §4);
    # rows that never activated (quarantined/rejected) are excluded
    return (
        "m.status NOT IN ('quarantined', 'rejected') "
        "AND m.recorded_at <= :as_of "
        "AND (m.superseded_at IS NULL OR m.superseded_at > :as_of) "
        "AND m.valid_from <= :as_of "
        "AND (m.valid_to IS NULL OR m.valid_to > :as_of)"
    )


def _filters_sql(scopes: list[str] | None, kinds: list[str] | None) -> str:
    parts = []
    if scopes:
        parts.append("m.scope = ANY(:scopes)")
    if kinds:
        parts.append("m.kind = ANY(:kinds)")
    parts.append("(m.scope != 'conversation' OR m.conversation_id = :conversation_id)")
    # §18.2: project rows are visible only under their own key; without a
    # key the equality is NULL ⇒ false — projects never leak sideways
    parts.append("(m.scope != 'project' OR m.project_key = CAST(:project_key AS text))")
    # §18.8 tenancy: another user's memories are invisible; unowned
    # (pre-auth / system) rows stay visible to everyone

    return (" AND " + " AND ".join(parts)) if parts else ""


def visibility_sql(
    *,
    scopes: list[str] | None = None,
    kinds: list[str] | None = None,
    conversation_id: UUID | None = None,
    project_key: str | None = None,
    as_of: datetime | None = None,
    auth_user_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """THE memory visibility predicate (M50, code-H5): status/time, scope,
    conversation, project (§18.2) and tenancy (§18.8) decided in one place
    and used by every retrieval path — recall's two legs and the pinned
    profile. A rule added here reaches all of them; there is no second
    copy to forget. Returns the WHERE fragment (aliased `m`) + its params."""
    where = _temporal_predicate(as_of) + _filters_sql(scopes, kinds)
    params: dict[str, Any] = {
        "scopes": scopes,
        "kinds": kinds,
        "conversation_id": conversation_id,
        "project_key": project_key,
        "as_of": as_of,
        "auth_user_id": auth_user_id,
    }
    # M55 (spec §20): the tenancy clause is the active provider's — its
    # fragment and its parameters, appended here so every read carries it
    from app.auth import memory_visibility

    fragment, tenancy_params = memory_visibility()
    if fragment:
        where += " AND " + fragment
        params.update(tenancy_params)
    return where, params


async def recall(
    query: str,
    *,
    scopes: list[str] | None = None,
    kinds: list[str] | None = None,
    conversation_id: UUID | None = None,
    project_key: str | None = None,
    k: int = 6,
    floor: float = 0.35,
    as_of: datetime | None = None,
    bump_access: bool = True,
) -> list[RecallHit]:
    """Top-k memories for a query under the composite score, floor-gated."""
    from app.memory.store import active_model_key
    from app.retrieval import _query_vector

    query = " ".join(query.split())
    if not query:
        return []
    # `concierge_memory_recall_seconds` was declared and never observed, so
    # the one latency the memory layer is judged on had no series behind it
    import time as _time

    from app import obs

    _t0 = _time.perf_counter()

    where, vparams = visibility_sql(
        scopes=scopes,
        kinds=kinds,
        conversation_id=conversation_id,
        project_key=project_key,
        as_of=as_of,
        auth_user_id=str(_auth_uid()) if _auth_uid() else None,
    )
    params: dict[str, Any] = {
        "q": or_tsquery(query),
        "qtext": query,
        "n": _CANDIDATES_PER_LEG,
        **vparams,
    }

    # the lexical leg's ABSOLUTE score is coverage: this row's cover-density
    # rank over the rank the query's own text would earn. Full coverage is
    # 1.0, half the query's lexemes ≈ 0.5, no match 0 — unlike raw
    # ts_rank_cd it is comparable across queries, which is what a floor needs.
    lexical_sql = sql_text(
        f"""
        SELECT m.id,
               LEAST(
                 COALESCE(
                   ts_rank_cd(m.fts, tsq)
                   / NULLIF(ts_rank_cd(to_tsvector('english', :qtext), tsq), 0),
                   0),
                 1.0) AS lex
        FROM memories m, to_tsquery('english', :q) tsq
        WHERE m.fts @@ tsq AND {where}
        ORDER BY ts_rank_cd(m.fts, tsq) DESC
        LIMIT :n
        """  # noqa: S608 — fragments are code constants; values are bound params
    )
    qvec = await _query_vector(query)
    model_key = await active_model_key() if qvec is not None else None
    # M54: the typed column (and its cast type) for the active key's dims —
    # what the HNSW index is built on; an unsupported dimension has no
    # vector leg (its rows were never embedded)
    from app.memory.dims import vector_column

    typed = vector_column(model_key) if model_key else None

    vector_leg = qvec is not None and model_key is not None and typed is not None

    async with get_session_factory()() as session:
        lex_rows = (await session.execute(lexical_sql, params)).all()
        lex_ids = [r[0] for r in lex_rows]
        lex_scores: dict[UUID, float] = {r[0]: float(r[1] or 0.0) for r in lex_rows}
        vec_ids: list[UUID] = []
        vec_scores: dict[UUID, float] = {}
        if qvec is not None and model_key is not None and typed is not None:
            col, vtype = typed
            vector_sql = sql_text(
                f"""
                SELECT m.id, 1 - (e.{col} <=> CAST(:qvec AS {vtype})) AS sim
                FROM memories m
                JOIN memory_embeddings e
                  ON e.ref_id = m.id AND e.table_ref = 'memories'
                 AND e.model_key = :model_key
                WHERE {where}
                ORDER BY e.{col} <=> CAST(:qvec AS {vtype})
                LIMIT :n
                """  # noqa: S608 — fragments are code constants; values are bound params
            ).bindparams(bindparam("qvec"), bindparam("model_key"))
            vec_rows = (
                await session.execute(
                    vector_sql,
                    {**params, "qvec": str(list(qvec)), "model_key": model_key},
                )
            ).all()
            vec_ids = [r[0] for r in vec_rows]
            # the similarity the leg already computes — carried through to
            # scoring instead of discarded with the rest of the row
            vec_scores = {r[0]: max(0.0, min(1.0, float(r[1]))) for r in vec_rows}

        # reciprocal-rank fusion over whichever legs exist — the candidate
        # union and the tiebreak, never the relevance score
        rrf: dict[UUID, float] = {}
        for ranking in ([lex_ids] if lex_ids else []) + ([vec_ids] if vec_ids else []):
            for i, mid in enumerate(ranking):
                rrf[mid] = rrf.get(mid, 0.0) + 1.0 / (_RRF_K + i + 1)
        if not rrf:
            obs.MEMORY_RECALL_SECONDS.observe(_time.perf_counter() - _t0)
            return []

        # ORM load by id — NEVER a raw `SELECT *` with positional column
        # mapping: a migrated DB's column order can differ from the model's
        # (found live in M31: project_key appended last shifted every later
        # column onto the wrong result processor)
        mem_rows = list(
            (await session.execute(select(Memory).where(Memory.id.in_(list(rrf.keys())))))
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        hits: list[RecallHit] = []
        # NOTE: a row can match lexically and still miss the lexical leg's
        # top-N cut; it then scores as vector-only. That is the candidate
        # budget showing through, not a scoring rule.
        weight_total = W_ABS_LEX + (W_ABS_VEC if vector_leg else 0.0)
        for mem in mem_rows:
            relevance = (
                W_ABS_LEX * lex_scores.get(mem.id, 0.0)
                + (W_ABS_VEC * vec_scores.get(mem.id, 0.0) if vector_leg else 0.0)
            ) / weight_total
            half_life_h = (
                float(mem.half_life_days) * 24 if mem.half_life_days else DEFAULT_HALF_LIFE_HOURS
            )
            anchor = mem.last_accessed_at or mem.recorded_at
            age_h = max((now - anchor).total_seconds() / 3600.0, 0.0)
            recency = math.exp(-math.log(2) / half_life_h * age_h)
            importance = mem.importance / 10.0
            score = (W_REL * relevance + W_REC * recency + W_IMP * importance) / (
                W_REL + W_REC + W_IMP
            )
            if mem.pinned or (relevance >= floor and score >= floor):
                hits.append(
                    RecallHit(
                        memory=mem,
                        score=round(score, 4),
                        relevance=round(relevance, 4),
                        recency=round(recency, 4),
                        importance=importance,
                    )
                )
        # deterministic order: composite score, then the fused rank (RRF's
        # remaining job), then the id — equal scores must not come back in
        # whatever order the result set happened to arrive in
        hits.sort(
            key=lambda h: (h.score, rrf.get(h.memory.id, 0.0), str(h.memory.id)), reverse=True
        )
        hits = hits[:k]

        # §16.7 entity hop: up to 2 extra active memories sharing an entity
        # with a top hit — reached by structure, not similarity, so they are
        # floor-exempt, scored at a fixed discount of the weakest direct hit,
        # and skipped for filtered (kinds) or point-in-time (as_of) recalls
        if hits and as_of is None and kinds is None:
            # the hop is a THIRD read path, so it reuses the very predicate
            # the two legs ran under — it used to hand-roll a conversation
            # clause and miss the project clause (§18.2) and the tenancy
            # fragment (§18.8) entirely, hopping across a project boundary.
            # `where` is already the right shape here: the hop only runs
            # with as_of=None (⇒ status='active') and kinds=None.
            hop_rows = (
                await session.execute(
                    sql_text(
                        f"""
                        SELECT DISTINCT m.id FROM memories m
                        JOIN memory_entity_links l1 ON l1.memory_id = m.id
                        JOIN memory_entity_links l2 ON l2.entity_id = l1.entity_id
                        WHERE l2.memory_id = ANY(:hit_ids)
                          AND m.id != ALL(:hit_ids)
                          AND {where}
                        LIMIT 2
                        """  # noqa: S608 — fragments are code constants; values are bound params
                    ),
                    {**vparams, "hit_ids": [h.memory.id for h in hits]},
                )
            ).all()
            hop_ids = [r[0] for r in hop_rows]
            if hop_ids:
                hop_score = round(min(h.score for h in hits) * 0.8, 4)
                hop_mems = list(
                    (await session.execute(select(Memory).where(Memory.id.in_(hop_ids))))
                    .scalars()
                    .all()
                )
                for mem in hop_mems:
                    hits.append(
                        RecallHit(
                            memory=mem,
                            score=hop_score,
                            relevance=0.0,
                            recency=0.0,
                            importance=mem.importance / 10.0,
                            linked=True,
                        )
                    )

        if bump_access and hits and as_of is None:
            await session.execute(
                update(Memory)
                .where(Memory.id.in_([h.memory.id for h in hits]))
                .values(last_accessed_at=now, access_count=Memory.access_count + 1)
            )
            await session.commit()

    obs.MEMORY_RECALL_SECONDS.observe(_time.perf_counter() - _t0)
    logger.info(
        "memory_recall",
        tier="memory",
        kind="recall",
        query_len=len(query),
        candidates=len(rrf),
        returned=len(hits),
        vector_leg=bool(vec_ids),
    )
    return hits


async def pinned_memories(
    conversation_id: UUID | None = None, project_key: str | None = None
) -> list[Memory]:
    """The always-injected profile rows (spec §16.3), newest first — under
    the SAME visibility predicate as recall (M50): scope, conversation,
    project and tenancy are decided once, in visibility_sql. Before M50
    pinned selection was a global query with a Python filter on scope —
    it leaked project rows across projects and never checked the owner."""
    where, params = visibility_sql(
        conversation_id=conversation_id,
        project_key=project_key,
        auth_user_id=str(_auth_uid()) if _auth_uid() else None,
    )
    pinned_sql = sql_text(
        f"SELECT m.id FROM memories m WHERE m.pinned AND {where} "  # noqa: S608 — fragments are code constants; values are bound params
        "ORDER BY m.recorded_at DESC"
    )
    async with get_session_factory()() as session:
        ids = [r[0] for r in (await session.execute(pinned_sql, params)).all()]
        if not ids:
            return []
        rows = list((await session.execute(select(Memory).where(Memory.id.in_(ids)))).scalars())
    order = {mid: i for i, mid in enumerate(ids)}
    return sorted(rows, key=lambda m: order[m.id])


def or_tsquery(query: str) -> str:
    """OR-joined tsquery source: recall ranks by ts_rank_cd over ANY matching
    term — websearch_to_tsquery's AND semantics let question boilerplate
    ("one short sentence") veto the real match (experiment finding, M17)."""
    import re as _re

    tokens = _re.findall(r"[a-z0-9]+", query.lower())
    seen: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.append(tok)
    return " | ".join(seen[:24]) or "x_no_terms"
