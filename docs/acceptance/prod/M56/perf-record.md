# performance record — 2026-09-10T22:37:17Z — base http://localhost:5174 (through the frontend proxy) — label v1
[22:37:17] at rest: {'connections': {'total': 14, 'idle': 14}, 'max_connections': 100}
[22:37:17] ── scenario api ──
[22:37:18] api GET /runs: p50 64.47 ms, errors {}
[22:37:19] api GET /conversations: p50 39.03 ms, errors {}
[22:37:20] api GET /skills: p50 53.14 ms, errors {}
[22:37:20] api GET /tools: p50 55.87 ms, errors {}
[22:37:21] api GET /settings: p50 27.72 ms, errors {}
[22:37:22] api GET /memories/recall: p50 61.49 ms, errors {}
[22:37:22] ── scenario runs-scale ──
[22:37:22] runs-scale 1017 runs GET /runs: p50 12.08 ms, 50415 bytes
[22:37:22] runs-scale 1017 runs GET /conversations: p50 8.26 ms, 9542 bytes
[22:37:23] runs-scale 10017 runs GET /runs: p50 12.7 ms, 50415 bytes
[22:37:23] runs-scale 10017 runs GET /conversations: p50 9.29 ms, 9592 bytes
[22:37:23] ── scenario chat ──
[22:37:23] chat: 5 concurrent runs on fake:scripted
[22:37:24] chat 5: statuses {'completed': 5} e2e p95 888.47 ms peak conns 19
[22:37:26] chat: 10 concurrent runs on fake:scripted
[22:37:28] chat 10: statuses {'completed': 10} e2e p95 2172.1 ms peak conns 23
[22:37:30] chat: 25 concurrent runs on fake:scripted
[22:37:36] chat 25: statuses {'completed': 25} e2e p95 5633.25 ms peak conns 24
[22:37:38] ── scenario sse ──
[22:37:38] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 5 open, probe ok 3/3 p50 12.72 ms, conns 14
[22:37:38] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 10 open, probe ok 3/3 p50 13.75 ms, conns 14
[22:37:38] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 15 open, probe ok 3/3 p50 11.11 ms, conns 14
[22:37:38] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 20 open, probe ok 3/3 p50 11.61 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 25 open, probe ok 3/3 p50 11.79 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 30 open, probe ok 3/3 p50 12.15 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 35 open, probe ok 3/3 p50 11.28 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 40 open, probe ok 3/3 p50 9.92 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 45 open, probe ok 3/3 p50 11.29 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 50 open, probe ok 3/3 p50 11.67 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 55 open, probe ok 3/3 p50 11.37 ms, conns 14
[22:37:39] sse /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3: 60 open, probe ok 3/3 p50 15.46 ms, conns 14
[22:37:54] sse /api/v1/ambient/stream: 3 open, probe ok 3/3 p50 46.04 ms, conns 12
[22:38:10] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 30044', 'runs': 'DELETE 10041', 'conversations': 'DELETE 141'}
[22:38:10] restoring settings: ['default_model']
[22:38:10] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M56/perf-v1.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M56/perf-v1.md

# Load baseline — v1

Captured 2026-09-10T22:37:17+00:00 at commit `8c093f8` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 14.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 64.47 | 224.64 | 229.91 | 25062 | {} |
| GET /conversations | 39.03 | 218.19 | 332.35 | 3206 | {} |
| GET /skills | 53.14 | 176.17 | 188.63 | 24701 | {} |
| GET /tools | 55.87 | 149.18 | 162.59 | 27891 | {} |
| GET /settings | 27.72 | 147.42 | 166.45 | 3329 | {} |
| GET /memories/recall | 61.49 | 163.37 | 179.53 | 2 | {} |

Peak connections during the sweep: 21

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1017 | 12.08 | 14.58 | 50415 | 8.26 | 9.37 |
| 10017 | 12.7 | 16.22 | 50415 | 9.29 | 10.11 |

## Concurrent chat runs (fake:scripted)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 5 | {'completed': 5} | 47.82 | 887.65 | 888.47 | 5.62 | 19 |
| 10 | {'completed': 10} | 435.57 | 1914.08 | 2172.1 | 4.59 | 23 |
| 25 | {'completed': 25} | 561.2 | 4391.86 | 5633.25 | 4.43 | 24 |

## SSE subscribers

### /api/v1/chat/stream/fbaed875-39f8-4a85-aa1d-25945b3976e3

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 5 | 3 | 12.72 | 14 |
| 10 | 3 | 13.75 | 14 |
| 15 | 3 | 11.11 | 14 |
| 20 | 3 | 11.61 | 14 |
| 25 | 3 | 11.79 | 14 |
| 30 | 3 | 12.15 | 14 |
| 35 | 3 | 11.28 | 14 |
| 40 | 3 | 9.92 | 14 |
| 45 | 3 | 11.29 | 14 |
| 50 | 3 | 11.67 | 14 |
| 55 | 3 | 11.37 | 14 |
| 60 | 3 | 15.46 | 14 |

Max streams with a healthy probe: **60**; first failure at None; recovery after close: 45.7 ms

### /api/v1/ambient/stream

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 3 | 3 | 46.04 | 12 |

Max streams with a healthy probe: **3**; first failure at 20; recovery after close: 138.9 ms

Paused run: `{'run_id': 'fbaed875-39f8-4a85-aa1d-25945b3976e3', 'status': 'paused_hitl', 'error': None}`

# end — 2026-09-10T22:38:10Z
