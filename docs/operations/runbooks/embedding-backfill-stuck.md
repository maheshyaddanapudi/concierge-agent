# Runbook — the embedding backfill is not finishing

**What it is.** §16.1 promises a **zero-downtime embedding-model switch**:
change `embedding_model` and recall keeps working while the new vectors are
built in the background. The mechanism is `memory_embedding_backfill`
(`app/memory/lifecycle.py`), an hourly advisory-locked job that embeds every
live row lacking a vector under the **active** model key — memories (active
*and* quarantined, so an approval is instantly retrievable), run digests, and
active plan exemplars. Old-key rows coexist and are never deleted; recall
flips by querying the active key.

The job is **bounded on purpose**: 500 rows per pass, 64 texts per embeddings
call, once an hour. A large store therefore takes many hours by design, and
"not finished yet" is usually not a fault. What *is* a fault is a backfill
that makes no progress, because until a row has a vector under the active
key it is **lexical-only** in recall — and, if `memory_forget_enabled` is on,
a tombstone with no embedding degrades the M44 suppression gate to hash+anchor
matching, which is exactly the gap M46 was built to close.

Tombstones are **deliberately not backfillable** — they keep no text, so
pre-switch tombstones stay on hash+anchor matching for good. Privacy over
recall, by design, not a bug to chase.

## The metric that reveals it

| Signal | Healthy | Stuck |
|---|---|---|
| log `memory_embedding_backfill` | one INFO per pass with `embedded` (up to 500) and `model_key` | absent for hours while rows are still missing — **the line is only emitted when `embedded > 0`, so silence alone is ambiguous** |
| `concierge_memory_ops_total{kind="backfill",status="ok"}` | increments **every** pass, including empty ones | flat ⇒ the job is not running at all |
| log `memory_backfill_dims_unsupported` | absent | WARNING with `model_key` — the model's dimension has no typed column, so the job returns 0 forever |
| `concierge_loop_errors_total{loop="memory"}` | flat | climbing ⇒ the job is raising |
| `GET /api/v1/memories/status` | outstanding count falling pass over pass | flat across hours |
| `concierge_spend_ceiling_refusals_total{kind="embedding"}` | flat | climbing ⇒ the job is declining on the spend ceiling |
| rows in `memory_embeddings` for the active `model_key` | rising | flat |

The clean way to ask "how much is left" is the query in **First checks** —
it is the same `~exists` the job itself uses.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/api/v1/memories/status" | python3 -m json.tool
curl -s "http://localhost:${PORT}/api/v1/settings" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:d[k] for k in ("memory_enabled","embedding_model","memory_forget_enabled","spend_ceiling_enabled")})'
docker compose logs --since 6h backend \
  | grep -E 'memory_embedding_backfill|memory_backfill_dims_unsupported|job_held_on_spend_ceiling'

# what the active key is, and what is still missing under it
docker compose exec db psql -U concierge -d concierge -c \
  "select model_key, count(*) from memory_embeddings group by 1 order by 2 desc;"
docker compose exec db psql -U concierge -d concierge -c \
  "select 'memories' t, count(*) from memories m
      where m.status in ('active','quarantined')
        and not exists (select 1 from memory_embeddings e
                        where e.ref_id=m.id and e.table_ref='memories'
                          and e.model_key=(select model_key from memory_embeddings
                                           order by 1 desc limit 1))
    union all select 'run_digests', count(*) from run_digests
    union all select 'plan_exemplars', count(*) from plan_exemplars where status='active';"

# has the job's clock advanced?
docker compose exec db psql -U concierge -d concierge -c \
  "select * from job_clock where job in ('memory:backfill');"
```

Distinguish:

1. **It is simply working through a large store.** `job_clock` advances
   hourly, `memory_embedding_backfill` logs `embedded: 500` each pass, the
   outstanding count falls by 500 an hour. Nothing to fix — 100k memories is
   about eight days at that rate.
2. **A gate closed it.** The job returns 0 immediately and silently when
   `memory_enabled` is **false** (the master is enforced inside the function,
   not only at the scheduler) or when `embedding_model` is **null** — the
   latter is the job's own gate, and null means "lexical-only, nothing to
   embed against". Both are legitimate states, not failures.
3. **The model's dimension has no column.** `memory_backfill_dims_unsupported`
   names the `model_key`. Typed columns exist for 64, 256, 384, 512, 768,
   1024, 1536 and 3072 dimensions (`halfvec` above 2000); a model of any other
   width has nowhere indexable to live and its rows stay lexical-only. Note
   the key is `provider:model@dims` — a key with **no** `@dims` suffix also
   resolves to no column.
4. **The spend ceiling is declining it.** `job_held_on_spend_ceiling` with
   `kind="embedding"` and `concierge_spend_ceiling_refusals_total{kind="embedding"}`
   climbing. The job declines quietly and retries next tick — see
   [spend-ceiling.md](./spend-ceiling.md).
5. **The embeddings provider is failing.** `concierge_loop_errors_total{loop="memory"}`
   climbing and the provider named in the log; the whole pass aborts, so
   `embedded` stays 0. Usually a key that is not configured for the provider
   the `embedding_model` ref names, or a rate limit.
6. **The leader never runs it.** `job_clock` is not advancing for
   `memory:backfill` at all while other jobs are. The periodic loop runs on
   the ambient leader — if no replica holds the lease, nothing ticks. See
   [leader-loss.md](./leader-loss.md).

## The action that resolves it

- Cause 1: wait, or force passes. The job is directly awaitable and enforces
  its own gates, so calling it repeatedly is safe; the cheapest lever is to
  leave it and let the hourly clock work.
- Cause 2: set `embedding_model` (Settings → Retrieval) and/or turn
  `memory_enabled` on. Until then, recall is lexical-only by definition —
  which is a supported mode, not a degraded one.
- Cause 3: choose a model whose dimension has a column, or ask for a
  supported width if the provider offers dimension reduction (Matryoshka
  models commonly do). Rows already embedded under the old key stay usable
  until you switch back — nothing is deleted.
- Cause 4: raise or disable the spend ceiling, or accept the delay: embedding
  is the cheapest thing on the ledger and will get its turn.
- Cause 5: fix the provider credential or the ref. `GET /api/v1/providers`
  shows which adapters are `configured`.
- Cause 6: restore the leader.

**Do not** delete the old model key's rows to "make room". They are what
recall is still serving from while the new key fills, and the switch is only
zero-downtime because both coexist.

## Recovery looks like

`memory_embedding_backfill` logging `embedded` each hour with the **active**
`model_key`, the outstanding count falling pass over pass to zero, the
`memory_embeddings` count under the active key matching the live row count,
and recall hits carrying real cosine scores rather than lexical-only ones.
