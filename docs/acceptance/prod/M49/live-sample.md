# Load baseline — live-sample

Captured 2026-09-10T21:31:48+00:00 at commit `8d5424c` against `http://localhost:8000`, model `openrouter:qwen/qwen3.8-max`.
Postgres `max_connections` = 100; connections at rest = 14.

## Concurrent chat runs (openrouter:qwen/qwen3.8-max)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 3 | {'completed': 3} | 26.89 | 5773.67 | 6726.13 | 0.44 | 14 |
| 6 | {'completed': 6} | 268.07 | 4824.61 | 6392.38 | 0.9 | 22 |

