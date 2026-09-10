# Load baseline — baseline

Captured 2026-09-01T22:30:03+00:00 at commit `68eafb7` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 11.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 30.33 | 191.31 | 265.0 | 1077 | {} |
| GET /conversations | 38.28 | 179.34 | 194.19 | 223 | {} |
| GET /skills | 38.69 | 181.24 | 202.27 | 21992 | {} |
| GET /tools | 41.03 | 180.86 | 195.11 | 25026 | {} |
| GET /settings | 23.84 | 176.96 | 249.33 | 2689 | {} |
| GET /memories/recall | 337.37 | 1284.48 | 2209.68 | 1980 | {} |

Peak connections during the sweep: 20

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1001 | 348.28 | 406.12 | 945863 | 343.98 | 371.7 |
| 10001 | 2190.61 | 2563.07 | 9468865 | 2392.78 | 2657.4 |

## Concurrent chat runs (fake:scripted)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 5 | {'completed': 5} | 79.23 | 1926.29 | 2006.73 | 2.48 | 15 |
| 10 | {'completed': 10} | 368.18 | 4091.47 | 4349.01 | 2.3 | 21 |
| 25 | {'completed': 25} | 1067.22 | 9591.65 | 9987.49 | 2.45 | 21 |
| 50 | {'completed': 50} | 2120.24 | 17642.41 | 18821.68 | 2.62 | 21 |

## SSE subscribers

### /api/v1/chat/stream/96f7627d-3716-4b6f-b10e-94c5e06ef1f0

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 5 | 3 | 8.44 | 12 |
| 10 | 3 | 8.84 | 17 |
| 15 | 0 | None | 21 |

Max streams with a healthy probe: **10**; first failure at 15; recovery after close: 42.3 ms

### /api/v1/ambient/stream

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 20 | 3 | 6.75 | 11 |
| 40 | 3 | 7.7 | 11 |
| 60 | 3 | 11.71 | 11 |
| 80 | 3 | 9.49 | 11 |
| 100 | 3 | 10.93 | 11 |
| 120 | 3 | 9.37 | 11 |

Max streams with a healthy probe: **120**; first failure at None; recovery after close: 46.6 ms

Paused run: `{'run_id': '96f7627d-3716-4b6f-b10e-94c5e06ef1f0', 'status': 'paused_hitl', 'error': None}`

## Memory recall by corpus size

| active memories | c=1 p50 ms | c=1 p95 ms | c=5 p95 ms | vector leg plan |
|---|---|---|---|---|
| 1003 | 18.08 | 33.53 | 56.81 | ['Seq Scan on memories', 'Seq Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |
| 10003 | 42.53 | 76.46 | 105.84 | ['Seq Scan on memories', 'Seq Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |
| 100003 | 123.11 | 511.87 | 811.32 | ['Seq Scan on memories', 'Seq Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |

## Ambient backlog

Fired 40 webhook events: codes {'202': 40}, fire p95 456.83 ms.
Drain of 40 accepted events: 62.97 s (0.64 events/s); verdicts {'fired': 40}.
Runs: {'completed': 40}, all terminal after 79.24 s; peak connections 29.

