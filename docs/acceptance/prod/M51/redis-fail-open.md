# M51 fail-open / delivery-retry / restart drill — 2026-09-10T22:33:11Z

$ docker compose --profile redis up -d redis; FAKE_LLM_ENABLED=1 REDIS_URL=redis://redis:6379/0 AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook docker compose up -d --force-recreate backend
 Container concierge-agent-redis-1 Running 
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 6s at http://localhost:8000
PATCH /settings → fake:scripted formatter False wall clock 900

$ §14n-74 PATCH /settings registry_cache_mode=redis; GET /cache/status; GET /tools ×3 (warm the redis path)
HTTP 200
{'mode': 'redis', 'tools': {'records': None, 'generation': 3, 'dirty': True, 'loaded_at': None, 'cached': False}}
GET /tools → HTTP 200 0.008433s
GET /tools → HTTP 200 0.006076s
GET /tools → HTTP 200 0.005674s
cache_degraded (before): none yet

$ docker compose --profile redis stop redis
 Container concierge-agent-redis-1 Stopped 

$ GET /tools, /skills, /sub-agents, /settings — served from Postgres
GET /tools → HTTP 200 0.008336s
GET /skills → HTTP 200 0.011358s
GET /sub-agents → HTTP 200 0.012851s
GET /settings → HTTP 200 0.004373s

$ POST /chat on the fake provider — a run still executes with redis down
{"queued":1,"pending":1}
run c32df232-8e5b-4c4a-a1ca-6c69e0b00794 → completed
concierge_cache_degraded_total{backend="redis"} 9.0
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-10T22:33:20.563284Z"}
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-10T22:33:20.632355Z"}
GET /cache/status with redis down → HTTP 200

$ docker compose --profile redis start redis; GET /tools ×2; registry_cache_mode back to bypass
 Container concierge-agent-redis-1 Started 
GET /tools → HTTP 200 0.008481s
GET /tools → HTTP 200 0.006229s
registry_cache_mode → bypass

$ §14n-75 backend env AMBIENT_WEBHOOK_URL (a closed port: every send is refused at once)
http://127.0.0.1:9/hook

$ PATCH /settings ambient on, tick 15 s, quiet hours off, interrupt → in_app + webhook
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_channels': {'interrupt': ['in_app', 'webhook']}, 'ambient_quiet_hours': []}
delivery_sends (before): none yet

$ insert one pending tier-0 delivery through the app's own add_delivery (inside the backend container)
delivery=3c0756fa-0525-4c4f-99b7-73bfff76c581
|22:33:24|interrupt|

$ wait for the tick to flush it (≤ 15 s): dispatched → webhook refused → committed delivered together with the ledger
attempts still 0 after 40 s
|22:33:24|interrupt|

$ attempt 2 on the real clock: backoff 60 s, retried on the first tick after it is due
attempts=2 after 70s
22:34:18|22:33:24|interrupt|{"at": "2026-09-10T22:35:18.748251+00:00", "ok": false, "dead": false, "error": "egress refused: denied", "attempts": 2, "next_attempt_at": "2026-09-10T22:40:18.748251+00:00"}

$ attempts 3 and 4: the 5-min and 30-min backoffs are skipped by moving next_attempt_at into the past (a clock skip, stated as such — not a code path); the fourth attempt dead-letters
attempts=3 after 15s
22:34:18|22:33:24|interrupt|{"at": "2026-09-10T22:35:33.841914+00:00", "ok": false, "dead": false, "error": "egress refused: denied", "attempts": 3, "next_attempt_at": "2026-09-10T23:05:33.841914+00:00"}
attempts=4 after 15s
22:34:18|22:33:24|interrupt|{"at": "2026-09-10T22:35:48.929109+00:00", "ok": false, "dead": true, "error": "egress refused: denied", "attempts": 4, "next_attempt_at": null}

$ dead-lettered (dead=true): a further clock skip changes nothing
22:34:18|22:33:24|interrupt|{"at": "2026-09-10T22:35:48.929109+00:00", "ok": false, "dead": true, "error": "egress refused: denied", "attempts": 4, "next_attempt_at": "2026-09-10T22:34:49+00:00"}
concierge_delivery_sends_total{channel="webhook",status="retry"} 3.0
concierge_delivery_sends_total{channel="webhook",status="dead"} 1.0
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 2, "dead": false, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-10T22:35:18.766446Z"}
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 3, "dead": false, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-10T22:35:33.859355Z"}
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 4, "dead": true, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-10T22:35:48.945073Z"}
restore ambient_channels → {} (in-app only)

$ §14n-73 part A: POST /_fake/script — one answer in 8 s (a short run), one in 300 s (a long one); POST /chat ×2; docker compose stop backend (SIGTERM; stop_grace_period 40 s > SHUTDOWN_GRACE_S 25 s)
{"queued":2,"pending":2}
short=d84d8f1c-a535-4d40-8412-6ab6ec13c0a0 (running)  long=d874dfae-4973-4719-8166-26650f811287 (running)
 Container concierge-agent-backend-1 Stopped 
stopped after 41s
(GET /ready while draining: uvicorn closes the listener at SIGTERM before the lifespan drain — a client sees connection refused, not the 503; the 503 is for a pre-stop probe, M53)
{"finished": 1, "cancelled": 1, "grace_s": 25.0, "event": "runs_drained", "level": "info", "timestamp": "2026-09-10T22:36:36.208592Z"}
INFO:     Application shutdown complete.

$ psql: the short run finished inside the grace; the long one is terminal — cancelled with the shutdown named — not left running
d84d8f1c|completed||22:36:17
d874dfae|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) — retr|22:36:36
plan|completed
plan|cancelled

$ docker compose start backend
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 4s at http://localhost:8000
non-terminal runs after the restart: 1

$ part B: two long answers, POST /chat ×2, then docker compose kill backend (SIGKILL — no drain possible)
{"queued":2,"pending":2}
89e5f46c|running||
504b7dcf|running||
plan|running
plan|running
 Container concierge-agent-backend-1 Killed 

$ psql: rows are still 'running' — the process died without a word
89e5f46c|running
504b7dcf|running

$ docker compose start backend — reap at boot: runs_orphaned_by_restart, the orphans failed with the truth, their steps cancelled
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 4s at http://localhost:8000
{"count": 2, "event": "runs_orphaned_by_restart", "level": "warning", "timestamp": "2026-09-10T22:37:01.907050Z"}
89e5f46c|failed|orphaned by a restart|22:37:01
504b7dcf|failed|orphaned by a restart|22:37:01
plan|cancelled
plan|cancelled
non-terminal runs after the restart: 1
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}

$ docker compose up -d --force-recreate backend (fake provider, REDIS_URL and the webhook sink off again); default_model back to openrouter:qwen/qwen3.8-max, tick 60 s
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000
default_model → openrouter:qwen/qwen3.8-max
# end — 2026-09-10T22:37:09Z
