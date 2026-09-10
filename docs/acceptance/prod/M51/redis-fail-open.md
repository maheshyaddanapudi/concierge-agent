# §14n-74 — Redis down, requests up

`registry_cache_mode=redis` with the compose `redis` profile, then `docker stop` on the redis container: every registry read keeps answering 200 from Postgres, a run still executes, `concierge_cache_degraded_total{backend="redis"}` counts the fallbacks, and the log names the backend and the error. Captured by `m51-redis.sh`.

```text

$ PATCH /settings registry_cache_mode=redis
HTTP 200

$ GET /cache/status
{'mode': 'redis', 'tools': {'records': None, 'generation': 2, 'loaded_at': None, 'cached': False}}

$ GET /tools ×3 (warm the redis path)
HTTP 200 0.009174s
HTTP 200 0.007975s
HTTP 200 0.007831s

$ GET /metrics cache_degraded (before)
(none yet)

$ docker stop concierge-agent-redis-1
stopped

$ GET /tools, /skills, /sub-agents, /settings — served from Postgres
GET /tools → HTTP 200 0.007144s
GET /skills → HTTP 200 0.012220s
GET /sub-agents → HTTP 200 0.010254s
GET /settings → HTTP 200 0.005591s

$ POST /chat on the fake provider — a run still executes with redis down
run b106f029-222b-49b5-86a1-ee41ce89e78e → completed

$ GET /metrics cache_degraded (after)
concierge_cache_degraded_total{backend="redis"} 19.0

$ backend log: cache_backend_degraded
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-02T00:12:48.660974Z"}
{"backend": "redis", "registry": "settings", "error": "Error -2 connecting to redis:6379. Name or service not known.", "event": "cache_backend_degraded", "level": "warning", "timestamp": "2026-09-02T00:12:48.706626Z"}

$ GET /cache/status with redis down
HTTP 200

$ docker start concierge-agent-redis-1
started
GET /tools → HTTP 200
GET /tools → HTTP 200

$ restore registry_cache_mode=bypass
bypass
```
