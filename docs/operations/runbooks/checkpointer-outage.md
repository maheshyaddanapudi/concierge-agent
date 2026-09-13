# Runbook — the checkpointer is unavailable

**What it is.** Durable graph state lives in LangGraph's own
`AsyncPostgresSaver` (`get_checkpointer()` in `backend/app/db.py`), on its
**own psycopg connection pool of 10** — separate from the SQLAlchemy pool,
and counted separately in the connection budget. Its three tables
(`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) are created by
`checkpointer.setup()` at boot; their schema belongs to
`langgraph-checkpoint-postgres`, not to this repo's Alembic chain.

Every orchestrated run compiles its graph **with** the checkpointer, so
without it nothing runs at all — this is not a HITL-only dependency. It is
what makes a `paused_hitl` run resumable: the thread is keyed by run id, and
`POST /runs/{id}/hitl` resumes from the stored state. A checkpointer outage
therefore has two faces: **runs failing at the first step** (no checkpointer
at all) and **paused runs that cannot be resumed** (the rows are gone or
unreadable while everything else works).

## The metric that reveals it

There is **no dedicated checkpointer metric or log event** — this is a known
gap, and it is why this page leans on the pool and the run record.

| Signal | Healthy | Outage |
|---|---|---|
| `concierge_runs_total{status="failed"}` | flat | steps up immediately when runs are started |
| `concierge_steps_total{status="failed"}` | flat | the **first** step of each run fails, before any tool call |
| a failed run's `error` (`GET /runs/{id}`) | — | names psycopg: `connection pool exhausted`, `relation "checkpoints" does not exist`, `the connection is closed` |
| `POST /runs/{id}/hitl` on a paused run | 200 `{status: "resuming"}` | 500, and the run stays `paused_hitl` |
| `concierge_db_pool_saturation` | under 1.0 | **normal** — the checkpointer pool is not in this gauge, so a healthy-looking pool does not clear the checkpointer |
| `GET /ready` | 200 `ok` | **200 `ok`** — the readiness probe checks the SQLAlchemy pool, not the checkpointer, so a balancer will keep routing here |
| `GET /replicas` → `budget` | `fits: true` | `fits: false`, or `needed` above the real `max_connections` |
| boot log | lifespan completes | startup raises in `get_checkpointer()` and the container restarts under `restart: unless-stopped` |

Those last three rows are the trap: **the platform looks ready.** Diagnose
from the run record, not from `/ready`.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')

# do the tables exist, and how big are they
docker compose exec db psql -U concierge -d concierge -c "\dt checkpoint*"
docker compose exec db psql -U concierge -d concierge -c \
  "select relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid)) size
     from pg_stat_user_tables where relname like 'checkpoint%' order by 3 desc;"

# who is connected, and is there room for ten more
docker compose exec db psql -U concierge -d concierge -c \
  "select count(*) used, current_setting('max_connections') max from pg_stat_activity;"
curl -s "http://localhost:${PORT}/api/v1/replicas" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["budget"])'

# what the failures actually say
curl -s "http://localhost:${PORT}/api/v1/runs?limit=10" \
  | python3 -c 'import json,sys;[print(r["id"], r["status"], repr(r.get("error"))[:160]) for r in json.load(sys.stdin)]'
docker compose logs --since 30m backend | grep -iE 'checkpoint|psycopg|pool'

# a paused run and its thread
docker compose exec db psql -U concierge -d concierge -c \
  "select id, status, started_at from runs where status='paused_hitl' order by started_at desc limit 5;"
docker compose exec db psql -U concierge -d concierge -c \
  "select thread_id, count(*) from checkpoints group by 1 order by 2 desc limit 5;"
```

Distinguish:

1. **Postgres is at `max_connections`** — the checkpointer pool cannot open
   its ten, so `get_checkpointer()` fails at boot or a checkout times out
   mid-run. `GET /replicas` → `budget` is the arithmetic: per replica it
   needs `DB_POOL_SIZE + DB_MAX_OVERFLOW + 10 (checkpointer) + 4 (session
   connections)`, plus a 10-connection reserve. If `fits: false`, this is it.
2. **The tables do not exist** — `\dt checkpoint*` is empty. Something
   dropped them (a partial restore that did not include them: `pg_dump` takes
   them like any other table, but a schema-filtered restore may not), or
   `checkpointer.setup()` never ran because boot failed earlier.
3. **The tables exist but the rows for a paused run are gone** — the run is
   `paused_hitl` and `checkpoints` has no `thread_id` for it. Causes:
   `retention_checkpoints_enabled` with a short `retention_checkpoints_days`
   trimming under a long-paused run (the purge is narrowest-first, but a
   7-day window against a run paused for eight days will take it), a restore
   from a dump older than the run, or a per-run delete/purge that removed it.
4. **A transaction-mode pooler in the path** — psycopg raises
   `DuplicatePreparedStatementError`. `DB_STATEMENT_CACHE_SIZE=0` fixes the
   *SQLAlchemy* pool; the checkpointer pool is a separate client and needs
   the pooler in session mode or a direct DSN.
5. **Postgres is simply down.** Then `/ready` *is* `degraded` and this is the
   database incident, not a checkpointer one.

## The action that resolves it

- Cause 1: raise Postgres `max_connections`, or lower `DB_POOL_SIZE` /
  `DB_MAX_OVERFLOW` / `DB_REPLICAS` until `GET /replicas` → `budget.fits` is
  true, then `./deploy.sh`. Sizing guidance in `../scaling.md`.
- Cause 2: restart the backend — `checkpointer.setup()` is idempotent and
  recreates them at boot. Runs that failed meanwhile are failed truthfully
  and can be retried (`POST /runs/{id}/retry`).
- Cause 3: the paused run **cannot be resumed** — its state is gone. Cancel
  it (`POST /runs/{id}/cancel`, which resolves a `paused_hitl` run as
  `cancelled`) and re-ask, rather than leaving a gate nobody can answer.
  Then raise `retention_checkpoints_days` above your longest expected pause,
  or turn `retention_checkpoints_enabled` off (it is born off for exactly
  this reason).
- Cause 4: put the checkpointer's DSN on a session-mode pooler or straight at
  Postgres.
- Cause 5: fix the database; `/ready` keeps this replica out of rotation
  meanwhile.

**Never** hand-edit or truncate the checkpoint tables to clear a stuck run.
The supported ways to remove checkpoint state are the ones that also settle
the run: `DELETE /runs/{id}`, `DELETE /runs` (purge), and the retention job —
all three take all three tables together, which is what keeps a checkpoint
from outliving the run it belongs to.

## Recovery looks like

New runs reach their second step, `concierge_steps_total{status="failed"}`
stops climbing, a `paused_hitl` run resumes on `POST /runs/{id}/hitl` and
reaches a terminal status, and `GET /replicas` → `budget.fits` is true with
`used` well under `max_connections`.

## Known gap

The checkpointer has no metric, no health probe and no named log event, and
`/ready` does not consult it — so an outage reads as ordinary run failures.
If you operate this in anger, the cheapest signal to add is a checkpointer
touch in the `/ready` probe (behind its own timeout, like the database one).
