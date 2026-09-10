# M51 fail-open / delivery-retry / restart drill — 2026-09-10T21:22:03Z

$ docker compose --profile redis up -d redis; FAKE_LLM_ENABLED=1 REDIS_URL=redis://redis:6379/0 AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook docker compose up -d --force-recreate backend
 Container concierge-agent-redis-1 Running 
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000
PATCH /settings → fake:scripted formatter False wall clock 900

$ §14n-74 PATCH /settings registry_cache_mode=redis; GET /cache/status; GET /tools ×3 (warm the redis path)
HTTP 200
{'mode': 'redis', 'tools': {'records': 41, 'generation': 1, 'dirty': True, 'loaded_at': '2026-09-10T21:22:09.627267+00:00', 'cached': True}}
GET /tools → HTTP 200 0.023619s
GET /tools → HTTP 200 0.007367s
GET /tools → HTTP 200 0.006751s
cache_degraded (before): none yet

$ docker compose --profile redis stop redis
 Container concierge-agent-redis-1 Stopped 

$ GET /tools, /skills, /sub-agents, /settings — served from Postgres
GET /tools → HTTP 200 0.007543s
GET /skills → HTTP 200 0.009969s
GET /sub-agents → HTTP 200 0.012557s
GET /settings → HTTP 200 0.004582s

$ POST /chat on the fake provider — a run still executes with redis down
{"queued":1,"pending":1}
run 678607ba-de01-4822-9a0e-bb9dee4cebe9 → completed
concierge_cache_degraded_total{backend="redis"} 9.0
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-10T21:22:12.496710Z"}
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-10T21:22:12.569491Z"}
GET /cache/status with redis down → HTTP 200

$ docker compose --profile redis start redis; GET /tools ×2; registry_cache_mode back to bypass
 Container concierge-agent-redis-1 Started 
GET /tools → HTTP 200 0.008301s
GET /tools → HTTP 200 0.006810s
registry_cache_mode → bypass

$ §14n-75 backend env AMBIENT_WEBHOOK_URL (a closed port: every send is refused at once)
http://172.18.0.1:9099/push

$ PATCH /settings ambient on, tick 15 s, quiet hours off, interrupt → in_app + webhook
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_channels': {'interrupt': ['in_app', 'webhook']}, 'ambient_quiet_hours': []}
delivery_sends (before): none yet

$ insert one pending tier-0 delivery through the app's own add_delivery (inside the backend container)
delivery=9e4ed0bc-4e62-40cd-9355-b5d79a9195d1
|21:22:16|interrupt|

$ wait for the tick to flush it (≤ 15 s): dispatched → webhook refused → committed delivered together with the ledger
attempts still 0 after 40 s
|21:22:16|interrupt|

$ attempt 2 on the real clock: backoff 60 s, retried on the first tick after it is due
attempts still 0 after 110 s
21:23:11|21:22:16|interrupt|

$ attempts 3 and 4: the 5-min and 30-min backoffs are skipped by moving next_attempt_at into the past (a clock skip, stated as such — not a code path); the fourth attempt dead-letters
attempts still 0 after 40 s
21:23:11|21:22:16|interrupt|
attempts still 0 after 40 s
21:23:11|21:22:16|interrupt|

$ dead-lettered (dead=true): a further clock skip changes nothing
21:23:11|21:22:16|interrupt|
(no delivery_sends series)
restore ambient_channels → {} (in-app only)

$ §14n-73 part A: POST /_fake/script — one answer in 8 s (a short run), one in 300 s (a long one); POST /chat ×2; docker compose stop backend (SIGTERM; stop_grace_period 40 s > SHUTDOWN_GRACE_S 25 s)
{"queued":2,"pending":2}
short=71902c2d-9caa-4ee4-bf4b-c63e76860026 (running)  long=73488420-7bee-4718-85de-8a75559e500c (running)
 Container concierge-agent-backend-1 Stopped 
stopped after 40s
(GET /ready while draining: uvicorn closes the listener at SIGTERM before the lifespan drain — a client sees connection refused, not the 503; the 503 is for a pre-stop probe, M53)
{"finished": 1, "cancelled": 1, "grace_s": 25.0, "event": "runs_drained", "level": "info", "timestamp": "2026-09-10T21:27:20.504479Z"}
INFO:     Application shutdown complete.

$ psql: the short run finished inside the grace; the long one is terminal — cancelled with the shutdown named — not left running
71902c2d|completed||21:27:02
73488420|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) — retr|21:27:20
plan|completed
plan|cancelled

$ docker compose start backend
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 4s at http://localhost:8000
non-terminal runs after the restart: 3

$ part B: two long answers, POST /chat ×2, then docker compose kill backend (SIGKILL — no drain possible)
{"queued":2,"pending":2}
9076b5a2|running||
4618d94f|running||
plan|running
plan|running
 Container concierge-agent-backend-1 Killed 

$ psql: rows are still 'running' — the process died without a word
9076b5a2|running
4618d94f|running

$ docker compose start backend — reap at boot: runs_orphaned_by_restart, the orphans failed with the truth, their steps cancelled
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 4s at http://localhost:8000
{"count": 2, "event": "runs_orphaned_by_restart", "level": "warning", "timestamp": "2026-09-10T21:27:46.264444Z"}
9076b5a2|failed|orphaned by a restart|21:27:46
4618d94f|failed|orphaned by a restart|21:27:46
plan|cancelled
plan|cancelled
non-terminal runs after the restart: 3
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}

$ docker compose up -d --force-recreate backend (fake provider, REDIS_URL and the webhook sink off again); default_model back to openrouter:qwen/qwen3.8-max, tick 60 s
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000
default_model → openrouter:qwen/qwen3.8-max
# end — 2026-09-10T21:27:54Z
