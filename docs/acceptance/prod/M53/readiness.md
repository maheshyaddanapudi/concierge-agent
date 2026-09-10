# §14p-84 — readiness, liveness and the polite close are separate facts

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ psql: a run owned by ANOTHER replica (inserted directly, status=running)
run 84adb81a-c627-4e7a-aab1-0853d2e6c068

$ GET /ready, /health before
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 8, "draining_since": null} HTTP 200
{"status":"ok"} HTTP 200

$ docker compose pause db → GET /ready 503 degraded (the db field names the failure) while /health stays 200; unpause → 200 again
 Container concierge-agent-db-1 Paused 
{"status": "degraded", "db": "error: TimeoutError", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 8, "draining_since": null} HTTP 503 in 2.004023s
{"status":"ok"} HTTP 200
 Container concierge-agent-db-1 Unpaused 
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 8, "draining_since": null} HTTP 200

$ docker compose kill -s USR1 backend
 Container concierge-agent-backend-1 Killing 
 Container concierge-agent-backend-1 Killed 

$ GET /ready → 503 draining; GET /health → 200
{"status": "draining", "db": "ok", "accepting": false, "running": 0, "queued": 0, "max_concurrent": 8, "draining_since": 1788317597.5749369} HTTP 503
{"status":"ok"} HTTP 200

$ POST /chat → 503 + Retry-After
HTTP/1.1 503 Service Unavailable
retry-after: 10
{"detail":"not accepting new runs: this replica is draining"}

$ GET /chat/stream/84adb81a-c627-4e7a-aab1-0853d2e6c068 (a run this process is not executing) → reconnect hint, stream closes
event: reconnect
data: {"reason": "draining", "retry_after_ms": 5000}
retry: 5000


$ GET /chat/stream/<a run completed by an EARLIER process>?after=3 during the drain → its terminal events come from the record (ids continue at 4), then the stream ends — no reconnect hint
id: 4
event: run_status
data: {"type": "run_status", "run_id": "5d413c99-59a1-421c-b9ed-450f079dfff8", "ts": "2026-09-02T02:53:18.791806+00:00", "payload": {"status": "completed"}, "se

id: 5
event: done
data: {"type": "done", "run_id": "5d413c99-59a1-421c-b9ed-450f079dfff8", "ts": "2026-09-02T02:53:18.791830+00:00", "payload": {"answer": "The capital of Portuga


$ docker compose up -d --force-recreate --no-deps backend (a drained process is replaced, never resumed)
 Container concierge-agent-backend-1 Started 
ready after 5s
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}

```
