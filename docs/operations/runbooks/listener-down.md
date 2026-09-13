# Runbook — a LISTEN connection is down

**What it is.** The process holds **three** dedicated Postgres sessions that
do nothing but `LISTEN` (they are outside the SQLAlchemy pool, by design —
see the connection budget in `../configuration.md`):

| Channel | Carries | Who reads it |
|---|---|---|
| `registry_cache_inv` | registry/settings invalidations from any replica | `app/registry_cache.py` |
| `ambient_events` | "an event landed, wake the drain" | `app/ambient/drain.py` |
| `concierge_control` | cancel intents, terminal transitions, in-app deliveries to re-fan | `app/control.py` |

Before M53 each was opened once at boot and never looked at again: a
Postgres restart, a failover, or an idle timeout on a NAT left the process
deaf for the rest of its life with nothing saying so. They are **supervised**
now — a lost connection reconnects with exponential backoff, and each
carries a hook that repairs what was missed while it was deaf (the cache
marks every registry dirty; the drain wakes immediately).

Nothing is lost when a listener is down, because **the notification is never
the truth** — the row is. A missed invalidation costs at most
`REGISTRY_CACHE_TTL_S` of staleness; a missed wake costs at most one ambient
tick; a missed control message is covered by the owner's heartbeat. What a
*persistently* down listener costs is timeliness, and in `memory` or `redis`
cache mode, cross-replica coherency down to the TTL.

## The metric that reveals it

| Signal | Healthy | Down |
|---|---|---|
| `concierge_listener_connected{channel}` | **1** for all three channels, on every replica | 0 for one or more |
| `concierge_listener_reconnects_total{channel}` | flat, or a step after a database restart | climbing steadily — a flapping connection, not a clean one |
| log `listener_connect_failed` | absent | WARNING with `channel`, sanitized `error`, `retry_in_s` (5 s doubling) |
| log `listener_lost` | absent | WARNING with `channel` and `retry_in_s` — the connection was up and went away |
| log `listener_reconnected` | one after a database restart | repeated |
| log `listener_reconnect_hook_failed` | absent | the reconnect succeeded but the owner's repair (cache dirty-marking, drain wake) raised |
| log `cache_listener_started` / `cache_listener_reconnected` / `cache_listener_unavailable` | `started` once at boot | `unavailable` at boot (the process runs single-node-correct but hears no peer), or `reconnected` repeating |
| `GET /api/v1/cache/status` | `dirty` empty | registries staying `dirty` in `memory`/`redis` mode |

Symptoms an operator notices first, before looking at metrics: a registry
edit made on one replica not visible on another until the TTL; an ambient
event sitting until the next tick instead of draining at once; a Stop
pressed on one replica taking up to a heartbeat to reach the run.

Not this: `concierge_listener_connected` has **no series at all** for a
channel that was never started — `ambient_events` is only listened to while
the ambient loop runs, so a stack with `ambient_enabled=false` shows two
channels, not three, and that is correct.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/metrics" | grep -E 'concierge_listener_'
docker compose logs --since 30m backend \
  | grep -E 'listener_(connect_failed|lost|reconnected|started|reconnect_hook_failed)'

# the sessions are NAMED so they can be told from the pool
docker compose exec db psql -U concierge -d concierge -c \
  "select pid, application_name, state, now()-backend_start as age, client_addr
     from pg_stat_activity where application_name like 'concierge-listen:%'
     order by application_name;"

# prove the wire end to end. The invalidation payload is `<origin>:<registry>`
# and a listener ignores its OWN origin, so use one no replica uses:
docker compose exec db psql -U concierge -d concierge -c \
  "select pg_notify('registry_cache_inv', 'manual-probe:tools');"
# then the registry should read dirty (memory/redis mode) within a moment:
curl -s "http://localhost:${PORT}/api/v1/cache/status" | python3 -m json.tool
```

Distinguish:

1. **Postgres restarted or failed over** — every replica logs `listener_lost`
   at the same second, then `listener_reconnected`. Normal; the hooks repair
   state. Nothing to do.
2. **The connection cannot be re-opened** — `listener_connect_failed`
   repeating with a growing `retry_in_s`. Read the sanitized error: at
   `max_connections` (the three session connections are outside the pool and
   are counted in the budget — `GET /replicas` → `budget`), credentials
   rotated, DNS, or a `DATABASE_URL` that a **transaction-mode pooler**
   answers — these sessions cannot go through one at all, they must reach
   Postgres directly.
3. **It reconnects constantly** — `listener_reconnects_total` climbing with
   no database restart. Something is killing idle sessions: a pooler's
   `server_idle_timeout`, a NAT/firewall idle cut, or a `pg_terminate_backend`
   sweep that does not exclude `application_name like 'concierge-listen:%'`.
4. **Connected but deaf** — the gauge reads 1, the sessions are in
   `pg_stat_activity`, and invalidations still do not land. Check that the
   replicas share **one** database: two stacks pointed at two databases each
   look perfectly healthy and never hear each other.

## The action that resolves it

- Cause 1: nothing. Confirm `listener_reconnected` for all three channels and
  that `cache/status` shows no lingering `dirty`.
- Cause 2: fix the budget or the credentials. If a pooler is in the path,
  give the listeners a direct DSN — they are session-scoped by nature, and
  `DB_STATEMENT_CACHE_SIZE=0` makes the *pooled* connections pooler-safe but
  does nothing for these.
- Cause 3: exclude the named sessions from whatever is reaping them, or
  lower the idle cut below the keepalive. The supervisor will keep
  reconnecting either way — this is a noise and timeliness problem, not a
  correctness one.
- Cause 4: confirm `DATABASE_URL` on every replica, then
  `POST /api/v1/cache/refresh/all` to force a reload now.
- **Immediate mitigation while any of this is true**: set
  `registry_cache_mode = "bypass"` (Settings → Registry cache). Bypass reads
  straight from Postgres and needs no invalidation at all, so a deaf
  listener cannot make a read stale. It is the documented rollback lever.

## Recovery looks like

`concierge_listener_connected` reads 1 for every channel the process runs, one
`listener_reconnected` line per channel and then silence,
`concierge_listener_reconnects_total` flat, `GET /cache/status` with no
`dirty` registries, and an edit on one replica visible on another within a
model call rather than within the TTL.
