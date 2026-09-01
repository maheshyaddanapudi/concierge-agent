# Load baseline — m50-after-runs

Captured 2026-09-01T23:14:30+00:00 at commit `b93e05b` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 13.

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1002 | 6.95 | 9.01 | 47133 | 6.01 | 7.47 |
| 10002 | 8.08 | 10.03 | 47133 | 8.3 | 11.23 |

