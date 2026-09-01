# M49 — foundation: measurement before fixes

Evidence for the first stage of the production-hardening program
(`docs/research/prod_hardening/PLAN.md`). Everything here was produced on the
shipped stack (`docker compose up`, fake provider enabled for the load
scenarios, `openrouter:qwen/qwen3.8-max` for the live sample) **before any
M50+ fix landed**, so the numbers are the ones later stages must beat.

| file | what it is |
|---|---|
| `baseline.json` / `baseline.md` | The load baseline: `experiments/load/harness.py` against the shipped API — read-path latency, `/runs` under 10× growth, concurrent chat runs, the SSE subscriber ceiling, recall by corpus size with the vector leg's query plan, the ambient webhook backlog, and the Postgres connection peak of each scenario |
| `baseline.log` | The harness's progress log for that run |
| `live-sample.json` / `live-sample.md` | The same `chat` scenario on the live model (`openrouter:qwen/qwen3.8-max`) at small concurrency — the end-to-end latency a user actually sees |
| `prompt-harness.md` | §14l-64: the prompt golden sets green, then a deliberate regression (a dropped binding sentence, a renamed placeholder) failing the harness with the prompt, case and cause named, then green again |
| `ruff-triage.md` | §14l-66: the 41 violations `BLE`/`S` surfaced, the decision on each, and the surviving-suppression inventory with executed lint/type/format proof |

## What the baseline says (headline findings, numbers in `baseline.md`)

- **The SSE ceiling is the connection pool.** `/chat/stream/{run}` holds a
  request-scoped DB session for the life of the stream. With the pool at
  its default 5 + 10 overflow, the probe request fails at the step that
  reaches 15 open streams; the same server holds 120 `/ambient/stream`
  subscribers (no session) without a wobble. This is `arch-C1` measured.
- **`/runs` and `/conversations` scale with the table, not the page.**
  Growing the run table 10× multiplies latency ~7× and the `/runs`
  payload reaches ~9 MB; `/conversations` pays the same because
  `run_count` loads every run of every conversation (`lazy="selectin"`).
  This is `arch-C2` / `code-H1` measured.
- **An ambient burst starves itself.** A webhook backlog is drained 20
  events per tick, every fired event spawns an executor that opens its
  own sessions, and the burst exhausts the same pool: most executions
  fail with `QueuePool limit … reached` and the tick itself fails once,
  so the remaining events wait for the next tick. This is `arch-C1` plus
  `code-H4` measured together.
- **Recall's vector leg is a sequential scan** over the untyped
  `Vector(None)` column, so latency grows with the corpus (`scale-B5`).
- **The fake-provider chat path is sound at 50 concurrent runs** — every
  run completes — but end-to-end latency grows linearly with concurrency
  because nothing bounds admission (M51).

## Reproduce

```bash
FAKE_LLM_ENABLED=1 docker compose up -d      # plus a db port mapping (5555:5432)
cd backend
.venv/bin/python ../experiments/load/harness.py --out ../docs/acceptance/prod/M49/baseline.json
.venv/bin/python ../experiments/load/harness.py --model openrouter:qwen/qwen3.8-max \
    --scenarios chat --chat-concurrency 3,6 --chat-deadline 240 \
    --label live-sample --out ../docs/acceptance/prod/M49/live-sample.json
python -m app.prompts.check
ruff check . && mypy app
```
