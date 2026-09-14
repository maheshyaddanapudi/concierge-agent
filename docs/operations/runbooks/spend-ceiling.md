# Runbook — spend ceiling reached

**What it is.** `spend_ceiling_enabled` puts **one** USD ceiling across
chat runs, direct invocations, ambient fires, eval batches, and five of the
out-of-run jobs. Two populations, and they are not the same set — see
**Known gap** at the foot of this page before you reason about totals:

- **Gated** (refused at the ceiling, `enforce_job_ceiling`): `overlap_judge`,
  `salience_judge`, `anticipation`, `reflection`, `community_summary`.
- **Ledgered** (counted in `usd_today` / `by_kind` via `job_spend`): those
  five plus `eval_judge` and `run_digest` — seven kinds in all.

Spend is summed from the database over
the **UTC day**, so every replica sees the same number, and it is priced
from usage the platform already records: each run step at its own model,
the remainder at the presentation model, an operator `model_prices`
override beating a provider-reported price beating the built-in table
(`app/llm/pricing.py`). A model none of them know is reported **unpriced**,
never guessed. The gate is off by default; off is the pre-M53 admission,
byte-identical.

Past the ceiling nothing is half-done: chat is refused before the run row
exists, an ambient fire is **held on its event** with the reason, an eval
batch stops, and a periodic job declines quietly and tries again next tick.
The day rolls over at 00:00 UTC and everything resumes on its own.

## The metric that reveals it

| Signal | Healthy | At the ceiling |
|---|---|---|
| `concierge_spend_usd_today` | below `spend_ceiling_usd_per_day` | at or above it |
| `concierge_spend_ceiling_refusals_total{kind}` | flat | climbing, labelled by what was refused. The label takes exactly nine values: the run kinds `chat`, `direct`, `ambient`, `eval` (`runner.py`), and the gated job classes `overlap_judge`, `salience_judge`, `anticipation`, `reflection`, `community_summary`. There is **no** `embedding`, `extraction`, `significance` or `eval_judge` series — those are not gated |
| `POST /chat` | 201 | **429** with `Retry-After` |
| `GET /api/v1/spend` | `ceiling.reached: false`, `ceiling.remaining` > 0 | `ceiling.reached: true`, `remaining` 0. The response also carries `day`, `usd_today`, `runs_today`, `unpriced_tokens` and `by_kind` — which is where the money went |
| log `spend_ceiling_refused` | absent | one WARNING per refused run, with `kind`, `usd_today`, `ceiling` |
| log `job_held_on_spend_ceiling` | absent | one INFO per declined periodic job (not an error — nobody is waiting on it) |
| log `ambient_fire_held_spend_ceiling` | absent | one WARNING per held fire; the event's `verdict` is `held` and `verdict_reason` names the ceiling |

Not the ceiling: a 429 from the **rate limiter** (`rate_limit_burst` /
`rate_limit_per_s`) carries the same status and a `Retry-After`, but no
`spend_ceiling_refusals_total` movement and no `spend_ceiling_refused` log
line. A 503 + `Retry-After` on `/chat` is admission shed, not spend.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/api/v1/spend" | python3 -m json.tool
curl -s "http://localhost:${PORT}/metrics" \
  | grep -E 'concierge_spend_usd_today|concierge_spend_ceiling_refusals_total'
docker compose logs --since 1h backend \
  | grep -E 'spend_ceiling_refused|job_held_on_spend_ceiling|ambient_fire_held_spend_ceiling'
# where the money went today, by model
docker compose exec db psql -U concierge -d concierge -c \
  "select model, count(*) steps, sum(input_tokens) tin, sum(output_tokens) tout
     from run_steps where started_at >= date_trunc('day', now() at time zone 'utc')
     group by 1 order by tout desc limit 15;"
# and the part that is not a run — the seven job_spend kinds only
# (extraction and embeddings are NOT in this table; see Known gap)
docker compose exec db psql -U concierge -d concierge -c \
  "select kind, model, count(*) calls, sum(input_tokens) tin, sum(output_tokens) tout,
          sum(cost_usd) usd, bool_and(cost_priced) all_priced
     from job_usage where at >= date_trunc('day', now() at time zone 'utc')
     group by 1,2 order by 5 desc;"
```

Distinguish:

1. **The ceiling is simply too low for the day's work** — spend rose
   smoothly, the models are the ones you expect, the refusals are spread
   across kinds.
2. **One job class is eating the budget** — `by_kind` in `GET /spend` (and
   the `job_usage` query above) shows one `kind` dominating. The kinds are
   exactly the seven `job_spend` call sites: `reflection` over a large
   store, `community_summary` rebuilding, `salience_judge` / `anticipation`
   on a busy ambient tick, `overlap_judge`, `eval_judge` on a batch, and
   `run_digest`. Note `eval_judge` and `run_digest` are counted but **not**
   gated, so they can carry the total past the ceiling that then refuses
   chat.
3. **A runaway loop** — one routine or one conversation accounts for most
   of it. `select trigger->>'routine_id' r, count(*), sum(total_output_tokens)
   from runs where started_at >= date_trunc('day', now() at time zone 'utc')
   group by 1 order by 3 desc;` names it.
4. **The number is wrong, not the spend** — a model with no price is
   reported unpriced, so real spend can exceed what the ceiling sees. Check
   `unpriced_tokens` in `GET /spend` before trusting a low figure; a nonzero
   count means some of the day is not in `usd_today` at all.

## The action that resolves it

- Cause 1: raise `spend_ceiling_usd_per_day` (Settings → Cost), or wait for
  00:00 UTC. Both take effect on the next run with no restart.
- Cause 2: turn that job's own gate off (Settings → Memory / Ambient — every
  autonomous behaviour has one, §3.7.1) or lower its budget, rather than
  raising the ceiling for everything. `memory_community_budget_tokens = 0`
  stops the community rebuild outright; `memory_reflection_enabled`,
  `memory_compaction_enabled`, `memory_extraction_learning`,
  `ambient_anticipation_enabled` and the two ambient learners are the usual
  suspects.
- Cause 3: pause the routine (`PATCH /routines/{id}` `status: "paused"`) or
  tighten its budgets (`ambient_runs_per_day`,
  `ambient_routine_events_per_hour`). A held fire stays on the ledger, so
  nothing is lost by pausing.
- Cause 4: add the missing price to `model_prices` (Settings → Cost) so the
  ceiling sees the real number. Prices are **not** retroactive — a finished
  run keeps the `price_snapshot` it was costed with, by design.
- To turn the ceiling off entirely: `spend_ceiling_enabled = false`. That is
  the pre-M53 behaviour — no ceiling anywhere — so prefer raising the number.

## Recovery looks like

`GET /api/v1/spend` reports `ceiling.reached: false`, `POST /chat` returns
201 again, `concierge_spend_ceiling_refusals_total` stops moving, and held
ambient events are re-evaluated on the next tick (the hold is on the event,
not a lost fire).

## Known gap

**Three classes of model spend are invisible to both the ceiling and the
ledger**, so `usd_today` is a floor, not a total. Verified against the code
this wave:

| Spend | Counted in `usd_today` / `by_kind`? | Refused at the ceiling? | Where it actually shows |
|---|---|---|---|
| Every **embedding** call (recall, write-through, the backfill) | **No** — `get_embeddings` (`app/llm/registry.py`) goes straight to the adapter with no `job_spend` | **No** — the backfill has no `enforce_job_ceiling` | nowhere |
| Memory **extraction** (`app/memory/extract.py`) | **No** — no `job_spend` around its `ainvoke` | **No** | nowhere |
| The ambient **significance** judge (`app/ambient/decide.py`) | **No** — it writes token counts only | **No** | `concierge_ambient_judge_tokens_total{direction}` — tokens, not USD |

Note that `record_job_usage`'s own docstring in `app/cost.py` claims to
cover "extraction and every embedding". It does not; the seven `job_spend`
call sites are the truth. Treat a suspiciously low `usd_today` on a stack
doing heavy embedding or extraction work as expected, not as a pricing bug
— and size the ceiling knowing that this spend sits outside it.

There is also **no metric or log event for a ceiling that is merely close**:
the only signals are the refusal counter and `concierge_spend_usd_today`,
which fire at or after the limit. Alert on
`concierge_spend_usd_today / spend_ceiling_usd_per_day` yourself if you want
warning before refusals start.
