# Runbook — Redis is down at runtime

**What it is.** Redis is **optional** and holds exactly one thing: the
`redis` backend of the registry cache (`registry_cache_mode = "redis"`,
`REDIS_URL`, `docker compose --profile redis up`). It is not a queue, not a
broker, not a session store, not a rate-limit store — the rate limiter lives
in Postgres (`rate_buckets`), and there is no other consumer. Spec §2 forbids
adding one.

So a Redis outage is a **degradation, not an incident**. Since M51 the cache
**fails open**: every read that Redis cannot serve falls through to Postgres,
which is the truth anyway, and a counter records that it happened. Runs keep
running, answers keep being correct, and the only cost is the per-read
database work the cache existed to avoid — the same cost `bypass` mode pays
deliberately.

## The metric that reveals it

| Signal | Healthy | Redis down |
|---|---|---|
| `concierge_cache_degraded_total{backend="redis"}` | flat | climbing — **one increment per read that fell through** |
| log `cache_backend_degraded` | absent | WARNING with `backend="redis"`, the `registry`, and the sanitized error |
| log `cache_redis_invalidate_failed` | absent | WARNING per invalidation Redis could not be told about (best-effort; Postgres is the truth) |
| `GET /api/v1/cache/status` | `mode: "redis"`, per-registry `records` / `generation` / `loaded_at` | still `mode: "redis"` — **the mode does not change itself** |
| `concierge_db_pool_saturation` | low | higher, steadily — every registry read is now a query |
| run latency | unchanged | a little worse per model call, no failures |
| `GET /ready` | 200 | **200** — Redis is not part of readiness, by design |

Not this: `PATCH /settings {"registry_cache_mode": "redis"}` returning **422
`redis unreachable: …`** is the *save-time* ping refusing to enter a mode it
cannot serve. That is the guard working, not an outage of a running cache.
And with `REDIS_URL` unset, the same PATCH is a 422 before any ping.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/metrics" \
  | grep -E 'concierge_cache_degraded_total|concierge_db_pool_saturation'
curl -s "http://localhost:${PORT}/api/v1/cache/status" | python3 -m json.tool
docker compose logs --since 15m backend \
  | grep -E 'cache_backend_degraded|cache_redis_invalidate_failed'

# is the service even meant to be running here?
docker compose ps redis
docker compose exec redis redis-cli ping        # expects PONG
grep -E '^(REDIS_URL|COMPOSE_PROFILES)=' .env
```

Distinguish:

1. **The container is not running** — `docker compose ps redis` is empty
   because `COMPOSE_PROFILES` does not include `redis` (a `docker compose up`
   without the profile, or a `.env` that lost it), while
   `registry_cache_mode` is still `redis` from an earlier session. Very
   common after a `decom`/re-setup.
2. **Redis is up but unreachable** — `redis-cli ping` from inside the network
   works, the backend's does not: a wrong `REDIS_URL` host (`redis` is the
   compose service name; `localhost` inside the backend container is the
   backend), or credentials in the URL that changed.
3. **Redis is up and refusing** — OOM (`maxmemory` reached with a
   `noeviction` policy), a paused instance, a failing AOF rewrite. `redis-cli
   info memory` and `redis-cli info persistence` say which.
4. **Nothing is wrong and this is a blip** — a handful of
   `cache_degraded_total` increments around a restart, then flat. The
   fail-open did its job; there is nothing to fix.

## The action that resolves it

- **First, decide whether you need Redis at all.** One process does not:
  `memory` mode is in-process and event-invalidated. Redis buys shared cache
  state across replicas, and even then `memory` mode is correct — a lost
  invalidation costs at most `REGISTRY_CACHE_TTL_S` (300 s) of staleness,
  because every entry expires on it.
- **Immediate mitigation, no restart**: `PATCH /api/v1/settings`
  `{"registry_cache_mode": "memory"}` — `memory` is the **shipped default**
  (`DEFAULTS` in `app/settings_store.py`) — or `"bypass"` for direct DB
  reads, which is the rollback lever rather than the default (it was the
  default through M56; see `../../adr/0004-registry-cache-bypass-default.md`).
  Both apply mid-process; flipping into `memory` warm-loads.
  `concierge_cache_degraded_total` stops moving at once. This is the right
  first move in any of causes 1–3.
- Cause 1: `COMPOSE_PROFILES=redis` in `.env` (that is what
  `./quick-setup.sh --redis` writes) and `docker compose up -d`, or leave it
  off and stay in `memory` mode.
- Cause 2: fix `REDIS_URL` — inside compose it is `redis://redis:6379/0`. The
  URL may carry credentials, so it stays **env-only** and is never in the
  database or the UI. A restart is needed for the env change; the mode flip
  above covers the gap.
- Cause 3: fix the instance (raise `maxmemory`, or set an eviction policy —
  the cache is a cache, `allkeys-lru` is appropriate), then flip the mode
  back and confirm with `POST /api/v1/cache/refresh/all`.
- Cause 4: nothing.

Note that the compose Redis binds to `127.0.0.1:6379` only and holds no
durable state of its own: losing it entirely costs nothing but the flip.

## Recovery looks like

`concierge_cache_degraded_total{backend="redis"}` flat again,
`GET /cache/status` reporting `cached: true` with a fresh `loaded_at` and no
lingering `dirty` registries, `redis-cli ping` → `PONG`, and
`concierge_db_pool_saturation` back to its pre-outage baseline.
