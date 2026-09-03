# Runbook — leader loss

**What it is.** One replica leads the ambient tick by holding a Postgres
session advisory lock on a dedicated connection (`spec §18.9`). The
evaluators run only on the leader; every replica drains. Leadership is lost
when the lease connection dies (the lock lapses with the session) or
released when the loop stops. Since M53 the shutdown path *awaits* the
loop, so a clean stop releases the lease immediately and the next replica
leads on its next tick; a crash lapses it when Postgres notices the dead
session.

## The metric that reveals it

| Signal | Healthy | Lost |
|---|---|---|
| `concierge_ambient_leader` (sum across replicas) | exactly 1 | 0 for longer than one tick |
| `concierge_ambient_ops_total{kind="drain"}` | increments on some replica | flat while `ambient_events` with no verdict exist |
| `concierge_listener_connected{channel="ambient_events"}` | 1 | 0 on a replica that also lost its wake channel (same database trouble) |
| log `ambient_leader_acquired` / `ambient_leader_lost` / `ambient_leader_error` | one `acquired` per handover | repeated `error` lines |

Two things look like leader loss and are not: **ambient is off**
(`ambient_enabled=false` — no replica leads by design, the gauge is 0
everywhere) and **two replicas both showing 1** (impossible with one
database; two stacks pointed at different databases).

## First checks

```bash
# M54: the fleet as the database sees it — which replicas are live
curl -s http://localhost:8000/api/v1/replicas | python3 -m json.tool
for h in backend-1 backend-2; do docker compose exec $h python -c \
  "import urllib.request;print('$h', urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode().split('concierge_ambient_leader ')[1][:3])"; done
docker compose exec db psql -U concierge -d concierge -c \
  "select pid, granted, now()-backend_start as age from pg_locks l join pg_stat_activity a using(pid) where locktype='advisory' and classid=427017;"
docker compose logs --since 5m backend | grep ambient_leader
# the supervised LISTEN sessions are named — the wake channel and the
# registry-cache channel — so they can be told from the pool
docker compose exec db psql -U concierge -d concierge -c \
  "select pid, application_name, state, now()-backend_start as age from pg_stat_activity where application_name like 'concierge-listen:%';"
```

Distinguish:

1. **The lock is held by a session nobody owns** — `pg_locks` shows it
   granted to a pid whose process is gone (a replica that was `kill -9`ed
   mid-tick, or a network partition). Postgres releases it when the TCP
   session times out — `tcp_keepalives_*` on the server decide how long.
2. **Every replica fails to acquire** — `ambient_leader_error` in the logs:
   the lease connection cannot be opened (database at `max_connections`,
   credentials rotated, DNS).
3. **Nothing is wrong** — a handover in progress; the gauge is 0 for at
   most one tick (`ambient_tick_interval_s`, 60 s by default).

## The action that resolves it

- Cause 1: `select pg_terminate_backend(<pid>)` on the orphaned session;
  the next tick on any replica acquires. Set Postgres
  `tcp_keepalives_idle/interval/count` low enough that a dead peer is
  noticed in under a tick.
- Cause 2: fix the database or its connection budget (`../scaling.md`);
  the loop retries every tick with no restart.
- Cause 3: wait one tick. If it persists past two ticks, treat as cause 1.

A stop-then-start of the leading replica (`./deploy.sh`) is always safe: the
lease is released on the way out (M53), and the M53 deploy evidence records
the handover time.

## Recovery looks like

`concierge_ambient_leader` sums to 1, `ambient_leader_acquired` logged once
on the new leader, the backlog gauge drains on the next tick.
