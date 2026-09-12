# Load baseline — ambient-burst

Captured 2026-09-10T21:30:41+00:00 at commit `8d5424c` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 14.

## Ambient backlog

Fired 40 webhook events: codes {'202': 40}, fire p95 409.07 ms.
Drain of 40 accepted events: 63.11 s (0.63 events/s); verdicts {'fired': 40}.
Runs: {'completed': 40}, all terminal after 66.12 s; peak connections 24.

