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

