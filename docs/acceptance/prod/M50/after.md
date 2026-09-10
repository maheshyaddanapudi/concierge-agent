# Load baseline — m50-after

Captured 2026-09-01T23:13:52+00:00 at commit `b93e05b` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 13.

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 10003 | 6.39 | 9.92 | 46790 | 7.96 | 9.4 |
| 10003 | 6.32 | 7.02 | 46790 | 8.39 | 9.15 |

## SSE subscribers

### /api/v1/chat/stream/78883339-8d6b-4223-a30e-aefc07fd1c8a

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 5 | 3 | 13.09 | 13 |
| 10 | 3 | 13.23 | 13 |
| 15 | 3 | 8.64 | 13 |
| 20 | 3 | 7.18 | 13 |
| 25 | 3 | 8.27 | 13 |
| 30 | 3 | 7.29 | 13 |
| 35 | 3 | 8.15 | 13 |
| 40 | 3 | 7.4 | 13 |
| 45 | 3 | 8.59 | 13 |
| 50 | 3 | 11.53 | 13 |
| 55 | 3 | 10.49 | 13 |
| 60 | 3 | 8.26 | 13 |

Max streams with a healthy probe: **60**; first failure at None; recovery after close: 33.5 ms

### /api/v1/ambient/stream

| streams open | probe ok/3 | probe p50 ms | db connections |
|---|---|---|---|
| 20 | 3 | 11.85 | 13 |
| 40 | 3 | 12.75 | 13 |
| 60 | 3 | 8.29 | 13 |
| 80 | 3 | 10.34 | 13 |
| 100 | 3 | 12.99 | 13 |
| 120 | 3 | 11.46 | 13 |

Max streams with a healthy probe: **120**; first failure at None; recovery after close: 43.4 ms

Paused run: `{'run_id': '78883339-8d6b-4223-a30e-aefc07fd1c8a', 'status': 'paused_hitl', 'error': None}`

