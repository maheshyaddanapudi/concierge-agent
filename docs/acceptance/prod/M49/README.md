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
| `ambient-burst-under-contention.md` | The backend log lines from the first, CPU-contended run: the same 40-event burst exhausting the connection pool (`ambient_execute_failed` × 34, `ambient_tick_failed`) — kept because the clean run did not reproduce it and the difference is the point |
| `live-sample.json` / `live-sample.md` | The same `chat` scenario on the live model (`openrouter:qwen/qwen3.8-max`) at small concurrency — the end-to-end latency a user actually sees |
| `prompt-harness.md` | §14l-64: the prompt golden sets green, then a deliberate regression (a dropped binding sentence, a renamed placeholder) failing the harness with the prompt, case and cause named, then green again |
| `ruff-triage.md` | §14l-66: the 41 violations `BLE`/`S` surfaced, the decision on each, and the surviving-suppression inventory with executed lint/type/format proof |

## What the baseline says (headline findings; full tables in `baseline.md`)

| finding | measured | review id |
|---|---|---|
| **The SSE ceiling is the connection pool.** `/chat/stream/{run}` holds a request-scoped DB session for the life of the stream. | 10 streams: probe healthy; 15 streams: probe fails 0/3 (pool 5 + 10 overflow all held); 120 `/ambient/stream` subscribers (no session): probe healthy, 11 connections | `arch-C1` |
| **`/runs` and `/conversations` scale with the table, not the page.** No pagination; `run_count` loads every run of every conversation (`lazy="selectin"`). | 1k runs: `/runs` p50 348 ms, 0.9 MB · 10k runs: p50 2191 ms, 9.5 MB · `/conversations` 344 → 2393 ms | `arch-C2` / `code-H1` |
| **Recall's vector leg is a sequential scan** over the untyped `Vector(None)` column, so latency grows with the corpus. | 1k memories: p50 18 ms · 10k: 43 ms · 100k: 123 ms (p95 512 ms; 811 ms at concurrency 5) — plan: `Seq Scan on memory_embeddings` at every size | `scale-B5` |
| **Nothing bounds admission.** 50 concurrent chat runs all complete, but end-to-end latency grows linearly with concurrency and submit latency itself reaches 2 s. | c=5: e2e p95 2.0 s · c=10: 4.3 s · c=25: 10.0 s · c=50: 18.8 s; ~2.5 runs/s throughout; peak 21 connections | M51 |
| **An ambient burst is drained 20 events per tick** and each fired event spawns its own executor with its own sessions. | 40 fires: 63 s to drain (0.64 events/s), 40/40 runs completed, peak 29 connections. Under CPU contention (the first run, overlapping the test suite — `ambient-burst-under-contention.md`) the same burst exhausted the pool: 34 of 40 executions failed with `QueuePool limit … reached` and the tick itself failed once | `arch-C1` + `code-H4` |
| Read path at rest is fine; recall with the live embedding model costs a network round trip per call. | p50 24–41 ms per endpoint; `/memories/recall` p50 337 ms with `openai:text-embedding-3-small` | — |
| **Live model sample** (`openrouter:qwen/qwen3.8-max`, graph mode with the formatter on): the end-to-end latency a user sees is the provider's, not the system's — and it still grows with concurrency. | c=3: e2e p50 8.3 s, p95 10.2 s · c=6: p50 11.4 s, p95 14.1 s; all 9 runs completed; 33 provider calls, all 200 | `live-sample.md` |

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
