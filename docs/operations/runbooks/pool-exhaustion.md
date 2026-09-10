# Runbook — database pool exhaustion

**What it is.** Every request and every run step borrows a connection from
the per-replica SQLAlchemy pool (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`, default
5 + 10). When all are out, the next borrower waits `DB_POOL_TIMEOUT` (30 s)
and then fails. Before M50 an open chat tab held a connection for its whole
life and 15 tabs emptied the pool; since M51 no session spans a provider
call, so the pool now empties only under a genuine write burst, a
long-running query, or a database that stopped answering.

## The metric that reveals it

| Signal | Healthy | Exhausted |
|---|---|---|
| `concierge_db_pool_saturation` | well under 1.0, spiky | pinned at 1.0 |
| `concierge_db_pool_connections{state="checked_out"}` | ≪ `{state="capacity"}` | equal to capacity |
| `concierge_db_pool_connections{state="overflow"}` | mostly 0 | at `DB_MAX_OVERFLOW` |
| `GET /ready` | 200 `ready`, `db: ok` | 503 `degraded` (`db: error: timeout`) — the probe itself could not borrow a connection in 2 s |
| `concierge_runs_in_flight{state="running"}` | ≤ `concierge_run_slots` | at the slot ceiling while steps stall |

Log lines: `sqlalchemy.exc.TimeoutError: QueuePool limit ... connection timed out`
in the run's `error`, and `step_finish` events with `status="failed"`.

## First checks

```bash
curl -s http://localhost:8000/metrics | grep -E 'concierge_db_pool|concierge_runs_in_flight|concierge_run_slots'
curl -s -i http://localhost:8000/ready
docker compose exec db psql -U concierge -d concierge -c \
  "select state, count(*) from pg_stat_activity where datname='concierge' group by 1;"
docker compose exec db psql -U concierge -d concierge -c \
  "select pid, now()-query_start as age, left(query,80) from pg_stat_activity where state<>'idle' order by 2 desc limit 10;"
```

Distinguish the three causes:

1. **Postgres is away or slow** — `pg_stat_activity` fails or shows long
   `age` on trivial queries; `/ready` is `degraded`. This is a database
   incident, not a pool one; the pool is the messenger.
2. **A runaway query** — one `pg_stat_activity` row with a large `age`
   (a huge `/runs` page before M50's pagination, an un-indexed scan on a
   new table).
3. **A genuine burst** — `checked_out` equals capacity, `running` equals
   `concierge_run_slots`, queries are short. The replica is simply over-
   subscribed.

## The action that resolves it

- Cause 1: fix the database. Meanwhile `/ready` keeps the replica out of
  rotation on its own; nothing to do on the backend.
- Cause 2: `select pg_cancel_backend(<pid>)` (then `pg_terminate_backend`
  if it does not yield). File the query: every list endpoint must page.
- Cause 3: lower `run_max_concurrent` (Settings → API guardrails) so fewer
  runs contend, or raise the budget — `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` in
  `.env` and a rolling deploy (`./deploy.sh`), keeping Postgres
  `max_connections ≥ replicas × (pool + overflow + 12)` (`../scaling.md`).

## Recovery looks like

`concierge_db_pool_saturation` falls under 1.0 and stays there, `/ready`
returns 200 `ready` with `db: ok`, runs that failed with the pool timeout
can be retried from the Runs page (they were `failed`, never lost).
