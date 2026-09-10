# v1.0.0 — performance record

The M49 harness (`experiments/load/`) against the v1.0.0 image at N=1 through the balancer (`:5174`), fake provider, clean settings (`planner_model` null, memory off, graph mode). Compare with `../M49/baseline.md` (before any fix) and `../M54/load-n3-vs-n1.md` (N=3). The first pass of this record was taken with the ceremony's `planner_model` still on the live model and is not the record (see the README).

```
# v1.0.0 performance record — 2026-09-10T01:39:20Z — base http://localhost:5174 (through the balancer), N=1
[01:39:20] at rest: {'connections': {'total': 12, 'idle': 12}, 'max_connections': 100}
[01:39:20] ── scenario api ──
[01:39:21] api GET /runs: p50 67.6 ms, errors {}
[01:39:22] api GET /conversations: p50 44.63 ms, errors {}
[01:39:23] api GET /skills: p50 55.17 ms, errors {}
[01:39:24] api GET /tools: p50 50.58 ms, errors {}
[01:39:24] api GET /settings: p50 33.36 ms, errors {}
[01:39:25] api GET /memories/recall: p50 106.22 ms, errors {}
[01:39:25] ── scenario runs-scale ──
[01:39:26] runs-scale 1012 runs GET /runs: p50 14.34 ms, 51233 bytes
[01:39:26] runs-scale 1012 runs GET /conversations: p50 8.49 ms, 9542 bytes
[01:39:27] runs-scale 10012 runs GET /runs: p50 15.48 ms, 51233 bytes
[01:39:27] runs-scale 10012 runs GET /conversations: p50 10.63 ms, 9592 bytes
[01:39:27] ── scenario chat ──
[01:39:27] chat: 5 concurrent runs on fake:scripted
[01:39:28] chat 5: statuses {'completed': 5} e2e p95 1079.13 ms peak conns 15
[01:39:30] chat: 10 concurrent runs on fake:scripted
[01:39:33] chat 10: statuses {'completed': 10} e2e p95 2679.73 ms peak conns 22
[01:39:35] chat: 25 concurrent runs on fake:scripted
[01:39:43] chat 25: statuses {'completed': 25} e2e p95 7931.16 ms peak conns 22
[01:39:45] ── scenario sse ──
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 5 open, probe ok 3/3 p50 17.23 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 10 open, probe ok 3/3 p50 16.02 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 15 open, probe ok 3/3 p50 13.29 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 20 open, probe ok 3/3 p50 14.41 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 25 open, probe ok 3/3 p50 13.0 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 30 open, probe ok 3/3 p50 13.0 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 35 open, probe ok 3/3 p50 12.42 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 40 open, probe ok 3/3 p50 13.32 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 45 open, probe ok 3/3 p50 12.37 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 50 open, probe ok 3/3 p50 13.51 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 55 open, probe ok 3/3 p50 12.73 ms, conns 12
[01:39:46] sse /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4: 60 open, probe ok 3/3 p50 14.52 ms, conns 12
[01:40:02] sse /api/v1/ambient/stream: 8 open, probe ok 3/3 p50 57.23 ms, conns 11
[01:40:24] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 30044', 'runs': 'DELETE 10041', 'conversations': 'DELETE 141'}
[01:40:24] restoring settings: ['ambient_enabled', 'default_model']
[01:40:24] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/perf-v1.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/perf-v1.md

# Load baseline — v1.0.0

Captured 2026-09-10T01:39:20+00:00 at commit `7e407cc` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 12.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 67.6 | 246.3 | 267.49 | 26935 | {} |
| GET /conversations | 44.63 | 223.26 | 237.27 | 2352 | {} |
| GET /skills | 55.17 | 215.76 | 232.03 | 24701 | {} |
| GET /tools | 50.58 | 313.06 | 466.0 | 27891 | {} |
| GET /settings | 33.36 | 194.41 | 210.18 | 3345 | {} |
| GET /memories/recall | 106.22 | 210.84 | 218.52 | 2 | {} |

Peak connections during the sweep: 18

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1012 | 14.34 | 17.81 | 51233 | 8.49 | 10.34 |
| 10012 | 15.48 | 18.33 | 51233 | 10.63 | 11.91 |

## Concurrent chat runs (fake:scripted)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 5 | {'completed': 5} | 86.99 | 963.82 | 1079.13 | 4.51 | 15 |
| 10 | {'completed': 10} | 294.58 | 2436.6 | 2679.73 | 3.72 | 22 |
| 25 | {'completed': 25} | 709.89 | 6257.97 | 7931.16 | 3.09 | 22 |

## SSE subscribers

### /api/v1/chat/stream/533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 5 | 3 | 17.23 | 12 |
| 10 | 3 | 16.02 | 12 |
| 15 | 3 | 13.29 | 12 |
| 20 | 3 | 14.41 | 12 |
| 25 | 3 | 13.0 | 12 |
| 30 | 3 | 13.0 | 12 |
| 35 | 3 | 12.42 | 12 |
| 40 | 3 | 13.32 | 12 |
| 45 | 3 | 12.37 | 12 |
| 50 | 3 | 13.51 | 12 |
| 55 | 3 | 12.73 | 12 |
| 60 | 3 | 14.52 | 12 |

Max streams with a healthy probe: **60**; first failure at None; recovery after close: 46.5 ms

### /api/v1/ambient/stream

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 8 | 3 | 57.23 | 11 |

Max streams with a healthy probe: **8**; first failure at 20; recovery after close: 119.6 ms

Paused run: `{'run_id': '533a3a0b-62bd-417c-bf2d-a69ed1e3b8e4', 'status': 'paused_hitl', 'error': None}`

# end — 2026-09-10T01:40:24Z
```
