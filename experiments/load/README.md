# Load harness

`harness.py` drives the **shipped API** of a running stack and records what
the system does under concurrency — read-path latency, run-table growth,
concurrent chat runs, the SSE subscriber ceiling, memory recall by corpus
size, and the ambient webhook backlog — plus the Postgres connection peak
for each, sampled from `pg_stat_activity`. It exists so every hardening
stage from M50 on has a number to beat, and so M56 can publish the
before/after record (`PLAN.md` in `docs/research/prod_hardening/`).

Nothing reaches into the process. The fake provider (`FAKE_LLM_ENABLED=1`
on the backend, spec §11) makes runs deterministic and key-free so the
numbers measure the system rather than a model; `--model` points the same
scenarios at a live model for an end-to-end sample.

## Run

```bash
# stack up with the fake provider enabled and the DB port published
FAKE_LLM_ENABLED=1 docker compose up -d      # plus a db port mapping, e.g. 5555:5432

cd backend
.venv/bin/python ../experiments/load/harness.py \
    --database-url postgresql://concierge:concierge@localhost:5555/concierge \
    --out ../docs/acceptance/prod/M49/baseline.json
```

Writes `baseline.json` (the full record) and `baseline.md` (the tables).
`--scenarios api,chat` narrows the run; `--keep-data` leaves the seeded
rows in place. Every seeded row carries the `loadgen` marker and the
settings the harness changes (`default_model`, `embedding_model`,
`memory_enabled`, `ambient_enabled`, the two ambient caps) are restored at
the end.

Live-model sample:

```bash
.venv/bin/python ../experiments/load/harness.py \
    --model openrouter:qwen/qwen3.8-max --scenarios chat --chat-concurrency 3,6 \
    --chat-deadline 240 --label live-sample --out ../docs/acceptance/prod/M49/live-sample.json
```

## What each scenario measures

| scenario | what it drives | the number |
|---|---|---|
| `api` | `--api-requests` GETs per endpoint at `--api-concurrency` | p50/p95/max per endpoint, error codes, connection peak |
| `runs-scale` | `/runs` and `/conversations` after seeding the run table to each `--runs-sizes` step | latency and payload bytes as rows grow — the 10× test |
| `chat` | `POST /chat` at each `--chat-concurrency` level, polled to a terminal state | submit latency, end-to-end latency, status split, runs/s, connection peak |
| `sse` | `/chat/stream/{run}` subscribers on a run paused at the seeded HITL gate, opened `--sse-step` at a time with a 3-request probe after each step; then `/ambient/stream` | streams open when the probe first fails, connection count per step, recovery time after close |
| `recall` | `/memories/recall` at each `--recall-sizes` corpus step (fake 64-dim vectors under `fake:scripted@64`) | p50/p95 at concurrency 1 and 5, and the vector leg's query plan (index or seq scan) |
| `ambient` | `--ambient-events` webhook fires on a throwaway routine | accepted/429 split, time-to-drain, events/s, fired/held verdicts, run outcomes |

## Reading the baseline

The baseline was captured **before** any M50+ fix on purpose. Expect it to
show the ceilings the reviews predicted: the SSE probe failing once the
pool (5 + 10 overflow) is held by streams, `/runs` latency and payload
growing linearly with the table, the vector leg running a sequential scan.
Later stages re-run the same command and commit the new record beside it.
