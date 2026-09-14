# ADR-0006: JSONB embedding storage before pgvector

Status: **Accepted, still in force for registry retrieval** — see *Addendum, 2026-09-14: pgvector arrived for a different consumer*

Date: 2026-08-07

> The decision recorded here is about the **registry retrieval vectors**
> (tools, skills, sub agents), and it stands unchanged: those are still JSONB
> columns scored in-process. What changed *around* it is that pgvector is now
> installed and used — by the §16 memory layer, a consumer that did not exist
> when this was written. The Context below argues from "no extension, stock
> image", which no longer describes the deployment. The record is left as
> written; the addendum says what is different now.

## Context

Hybrid retrieval (ADR-0005) needs a vector per registry record. The standard
answer is pgvector — but pgvector requires a non-stock Postgres image (or an
extension install step), an index strategy, and query-side ANN plumbing. At
POC scale the entire catalog already sits in the registry cache snapshot and
is scored in-process; the database is never asked a similarity question.
Adding pgvector would have complicated the three-service compose stack
(ADR-0001) to accelerate a query nobody runs.

## Decision

- Embeddings are stored as **JSONB float arrays** on the registry rows
  themselves: `embedding` + `embedding_hash` columns on tools, skills, and
  sub_agents (the models map `list[Any] → JSONB` via the declarative
  `type_annotation_map` in `backend/app/models/base.py`). The stock
  `postgres:16` image keeps working; no extension, no new service.
- Cosine similarity is computed in-process over the cache snapshot, next to
  BM25 (ADR-0005). The `embedding_hash` (SHA-256 of the embedded text)
  makes re-embedding idempotent: unchanged text is never re-sent.
- Embedding **generation lives on the provider port** (ADR-0002):
  `supports_embeddings()` / `get_embeddings(model, texts)` with the single
  entry point `get_embeddings("provider:model", texts)`. OpenAI and Google
  adapters implement it; **Anthropic reports unsupported and raises** —
  consumers degrade to lexical-only scoring, silently. Embeddings are
  maintained best-effort on the write path (failure logs and leaves the row
  unembedded, never fails the save) plus a startup backfill.
- **pgvector is the documented storage swap**, not a rejected option: when
  catalogs outgrow in-memory ranking, the JSONB column migrates to a
  `vector` column and scoring moves database-side. Spec §7.3 records this
  explicitly so the future migration is a planned step, not a rewrite.

## Consequences

Positive:

- Zero new infrastructure; the compose stack and CI images are untouched.
- Retrieval works with any embedding provider or none — an Anthropic-only
  deployment still gets BM25 ranking with no configuration.
- The swap path is clean: storage format changes, but `embed_text_for()`,
  hashing, and the write-path hooks all survive a pgvector migration.

Negative:

- In-process cosine is O(records × dimensions) per query; past a few
  thousand records this visibly costs latency and the migration becomes
  due — the design deliberately defers, it does not solve.
- JSONB float arrays are storage-inefficient versus a packed vector type,
  and Postgres cannot index them for similarity at all.
- Best-effort write-path embedding means rows can silently lack vectors
  (provider outage, missing key); ranking quality then varies per row in a
  way that is only visible in logs.

## Addendum — 2026-09-14: pgvector arrived for a different consumer

**What is unchanged.** Every clause of the Decision above still describes the
code. `tools`, `skills` and `sub_agents` still carry `embedding` +
`embedding_hash` mapped to JSONB through `type_annotation_map = {dict[str,
Any]: JSONB, list[Any]: JSONB}` in `backend/app/models/base.py`. Cosine is
still computed in-process over the registry-cache snapshot next to BM25, with
no similarity query ever sent to Postgres, and no index on those columns.
Embedding generation still lives on the provider port, and Anthropic still
reports unsupported so consumers degrade to lexical-only.

**What changed.** The premise "no extension, no new service" is no longer a
description of the deployment:

- `docker-compose.yml` runs **`pgvector/pgvector:0.8.6-pg16`**, not stock
  `postgres:16`, and migration `a1b2c3d4e5f6` executes `CREATE EXTENSION IF
  NOT EXISTS vector` (plus `btree_gist`).
- The §16.1 memory layer stores its vectors in a real pgvector table,
  `memory_embeddings`: eight typed columns (`emb_64` … `emb_1536` as
  `vector(n)`, `emb_3072` as `halfvec`), each with its own HNSW cosine index,
  added by migration `s8g9h0i1j2k3`. That is what makes the zero-downtime
  embedding-model switch possible — several dimensions coexist under
  different `model_key`s and recall flips by querying a different column.

**Why this does not reopen the decision.** The two cases have different
shapes, and that is the whole point. A registry is a few hundred rows that
are *already resident* in the cache snapshot the orchestrator holds — an ANN
index would accelerate a query nobody issues. Memories are an unbounded,
growing corpus queried by similarity on the recall path, where the index is
load-bearing. The cost this ADR was avoiding — a non-stock image and an
extension — has since been paid for the consumer that needed it, so the
"Negative" bullet about the eventual registry migration is now **cheaper**
than it was when written: the extension is present, and the swap is a column
type change plus query-side plumbing, with no infrastructure step attached.
It remains deferred, not done.

## References

- spec.md §2.1 (embeddings on the port), §7.3 ("pgvector remains a
  documented storage swap"), §7.4 (lexical-only degradation)
- /home/user/concierge-agent/backend/app/models/base.py, tool.py, skill.py,
  sub_agent.py (embedding columns)
- /home/user/concierge-agent/backend/app/retrieval.py (`embed_text_for`,
  `text_hash`, cosine + RRF)
- /home/user/concierge-agent/backend/app/llm/adapters.py (per-provider
  `get_embeddings`, Anthropic unsupported)
- Related: ADR-0002 (provider port), ADR-0005 (hybrid retrieval)
