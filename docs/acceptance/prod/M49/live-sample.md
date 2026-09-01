# Load baseline — live-sample

Captured 2026-09-01T22:52:09+00:00 at commit `d687689` against `http://localhost:8000`, model `openrouter:qwen/qwen3.8-max`.
Postgres `max_connections` = 100; connections at rest = 13.

## Concurrent chat runs (openrouter:qwen/qwen3.8-max)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 3 | {'completed': 3} | 35.73 | 8273.94 | 10157.4 | 0.29 | 13 |
| 6 | {'completed': 6} | 314.83 | 11416.12 | 14121.16 | 0.41 | 20 |

