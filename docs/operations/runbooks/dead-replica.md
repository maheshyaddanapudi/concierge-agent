# Runbook — a replica died (or vanished)

**What it is.** One backend process of several stopped — crashed, was
OOM-killed, lost its network — without the M53 drain. Since M54 (spec
§18.9) the fleet notices on its own: the replica's row in `replicas`
stops being refreshed, it is **dead after 45 s**, and everything it owned
is reconciled by whoever is left.

## What happens without you

| Owned by the dead replica | Reconciled by | When |
|---|---|---|
| runs it was executing or had queued (`runs.owner_replica`) | the periodic loop on any live replica: status `failed`, error `owner replica gone: <id> stopped heartbeating — retry it` | within the 60 s tick after the 45 s cutoff |
| chat streams it was serving | the browser reopens through the balancer (M53 client); the new replica serves the record once the row is failed | as above |
| the ambient leader lease, if it held it | lapses with its Postgres session; another replica leads on its next tick | one tick (`ambient_tick_interval_s`) |
| its ambient stream subscribers (the delivery audience) | its `subscribers` count stops counting once the row is dead | 45 s |
| its MCP subprocesses | gone with the process; every other replica holds its own | — |
| its share of the connection budget | released by Postgres when the sockets close (or `tcp_keepalives_*` notice) | seconds to minutes |

## The metric that reveals it

| Signal | Healthy | Dead replica |
|---|---|---|
| `GET /replicas` → `live` | true for every expected replica | false on one row, `heartbeat_at` frozen |
| `concierge_replica_info{replica}` (per target) | one target per replica | a target Prometheus stops scraping (`up == 0`) |
| `runs_reaped_dead_owner` in the logs | absent | `count` of the runs failed on its behalf |
| `concierge_runs_total{status="failed"}` | flat | a step of that size |

## First checks

```bash
curl -s http://localhost:8000/api/v1/replicas | python3 -m json.tool
docker compose ps backend                       # which container is gone
docker compose logs --since 10m backend | grep -E "runs_reaped_dead_owner|ambient_leader_acquired|replica_heartbeat_failed"
curl -s "http://localhost:8000/api/v1/runs?status=failed&limit=20" | grep -c "owner replica gone"
```

Distinguish:

1. **The process is gone** — `docker compose ps` shows it exited; `restart: unless-stopped` brings it back with a new hostname (a new replica id). Its old row lapses; nothing to clean.
2. **The process is alive but cannot reach Postgres** — its heartbeat fails (`replica_heartbeat_failed`, `concierge_loop_errors_total{loop="replica"}`), so the fleet treats it as dead and fails its runs while it may still be executing them against a database it cannot reach. When it reconnects, its runs' finalizers will find rows already `failed` — the record stays truthful (the reaper's verdict wins; the run's own late completion does not overwrite a terminal status).
3. **Nothing is wrong** — a slow scrape or a replica mid-restart; `live` returns within 45 s.

## The action that resolves it

- Cause 1: nothing, beyond retrying the failed runs from the Runs page if they matter. If the replica does not come back, the fleet is one smaller: check `GET /replicas` → `budget` still fits, and the load the survivors carry (`concierge_runs_in_flight`).
- Cause 2: fix the network or the database (`pool-exhaustion.md`, `leader-loss.md`); the replica rejoins by itself.
- Cause 3: wait 45 s.

## Recovery looks like

`GET /replicas` shows every expected replica `live`, no new `runs_reaped_dead_owner` lines, the leader gauge sums to 1, and the failed runs — if retried — complete on their new owner.
