# §14n-73 — restart mid-run leaves nothing half-alive

Part A: SIGTERM (`docker stop`, compose `stop_grace_period: 30s`) with a short and a long fake run in flight — the drain lets the short one finish inside `SHUTDOWN_GRACE_S` (25 s) and cancels the long one with the shutdown named in its error. Part B: SIGKILL with two runs in flight — the rows stay `running` until the next boot reaps them as failed "orphaned by a restart" with their steps cancelled. Zero non-terminal rows after either. Captured by `m51-restart.sh`.

```text

$ PATCH /settings default_model=fake:scripted, wall clock 900
fake:scripted

$ POST /_fake/script — one answer in 8 s (a short run), one in 300 s (a long one)
{"queued":2,"pending":2}
short=df2b714e-b3db-49af-89b2-3a738197a113 (running)  long=e8638f2e-4999-432a-a1bb-59d1daf21b6e (running)

$ docker stop (SIGTERM; compose stop_grace_period 30s > SHUTDOWN_GRACE_S 25s)

$ GET /ready while draining (uvicorn closes the listener at SIGTERM, before the lifespan drain — a client sees connection refused, not the 503; the 503 is for a pre-stop probe, M53)

$ POST /chat while draining
stopped after 30s

$ backend log: the drain
{"finished": 1, "cancelled": 1, "grace_s": 25.0, "event": "runs_drained", "level": "info", "timestamp": "2026-09-02T00:13:17.697286Z"}
INFO:     Waiting for application shutdown.
{"finished": 1, "cancelled": 1, "grace_s": 25.0, "event": "runs_drained", "level": "info", "timestamp": "2026-09-02T00:13:17.697286Z"}
INFO:     Application shutdown complete.

$ psql: the short run finished inside the grace; the long one is terminal, not left running
df2b714e|completed||00:13:00
e8638f2e|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) — retry it|00:13:17

$ docker start
healthy after 4s

$ psql: non-terminal runs after the restart
0

$ POST /_fake/script — two long answers, then POST /chat ×2, then SIGKILL
{"queued":2,"pending":2}
k1=88881b09-48e8-4460-8d28-b1e3a7dab298 (running)  k2=d17d6a0b-a54b-4354-9ea4-fb126ec8accb (running)
88881b09|running
d17d6a0b|running
plan|running
plan|running

$ docker kill (SIGKILL — no drain possible)

$ psql: rows are still 'running' — the process died without a word
88881b09|running
d17d6a0b|running

$ docker start — reap at boot
healthy after 4s
{"count": 2, "event": "runs_orphaned_by_restart", "level": "warning", "timestamp": "2026-09-02T00:13:34.396812Z"}

$ psql: the orphans are failed with the truth, their steps cancelled
88881b09|failed|orphaned by a restart|00:13:34
d17d6a0b|failed|orphaned by a restart|00:13:34
plan|cancelled
plan|cancelled

$ psql: non-terminal runs after the restart
0

$ GET /ready
{"status": "ready", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0}
```
