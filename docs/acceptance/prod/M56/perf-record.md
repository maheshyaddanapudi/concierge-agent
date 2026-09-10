# performance record — 2026-09-10T22:32:01Z — base http://localhost:5174 (through the frontend proxy) — label v1
[22:32:02] at rest: {'connections': {'total': 11, 'idle': 11}, 'max_connections': 100}
[22:32:02] ── scenario api ──
[22:32:03] api GET /runs: p50 58.22 ms, errors {}
[22:32:03] api GET /conversations: p50 42.2 ms, errors {}
[22:32:04] api GET /skills: p50 62.36 ms, errors {}
[22:32:05] api GET /tools: p50 40.69 ms, errors {}
[22:32:05] api GET /settings: p50 27.66 ms, errors {}
[22:32:06] api GET /memories/recall: p50 37.38 ms, errors {}
[22:32:06] ── scenario runs-scale ──
[22:32:06] runs-scale 1012 runs GET /runs: p50 12.49 ms, 51636 bytes
[22:32:06] runs-scale 1012 runs GET /conversations: p50 7.6 ms, 9542 bytes
[22:32:07] runs-scale 10012 runs GET /runs: p50 13.34 ms, 51636 bytes
[22:32:07] runs-scale 10012 runs GET /conversations: p50 9.44 ms, 9592 bytes
[22:32:07] ── scenario chat ──
[22:32:07] scenario chat failed: RuntimeError('PATCH settings {\'default_model\': \'fake:scripted\'} -> 422 {"detail":"default_model: provider \'fake\' is not configured (API key env var missing)"}')
[22:32:07] ── scenario sse ──
[22:32:07] scenario sse failed: RuntimeError('PATCH settings {\'default_model\': \'fake:scripted\'} -> 422 {"detail":"default_model: provider \'fake\' is not configured (API key env var missing)"}')
[22:32:23] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 30000', 'runs': 'DELETE 10000', 'conversations': 'DELETE 100'}
[22:32:23] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M56/perf-v1.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M56/perf-v1.md

# Load baseline — v1

Captured 2026-09-10T22:32:02+00:00 at commit `770593c` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 11.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 58.22 | 191.13 | 215.53 | 21707 | {} |
| GET /conversations | 42.2 | 164.44 | 204.14 | 2352 | {} |
| GET /skills | 62.36 | 154.8 | 167.51 | 13502 | {} |
| GET /tools | 40.69 | 150.42 | 162.48 | 27891 | {} |
| GET /settings | 27.66 | 144.13 | 155.86 | 3345 | {} |
| GET /memories/recall | 37.38 | 173.67 | 183.34 | 2 | {} |

Peak connections during the sweep: 17

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1012 | 12.49 | 15.87 | 51636 | 7.6 | 8.34 |
| 10012 | 13.34 | 17.71 | 51636 | 9.44 | 10.63 |

## SSE subscribers

## chat: error

`RuntimeError: PATCH settings {'default_model': 'fake:scripted'} -> 422 {"detail":"default_model: provider 'fake' is not configured (API key env var missing)"}`

## sse: error

`RuntimeError: PATCH settings {'default_model': 'fake:scripted'} -> 422 {"detail":"default_model: provider 'fake' is not configured (API key env var missing)"}`

# end — 2026-09-10T22:32:23Z
