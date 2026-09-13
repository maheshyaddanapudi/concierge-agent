# Backup and restore — the drill

The database is the whole application state (registries, conversations,
runs and steps, settings, memories and their vectors, the ambient ledgers,
LangGraph checkpoints); the `workspace` volume holds files runs wrote through
the filesystem MCP server; `.env` holds the secrets. A backup is a logical
dump of the first, a tarball of the second, and a copy of the third kept
where secrets are kept. This page is the procedure **as exercised**, with
the time it took — not a design note.

## Scripts

| Script | Does | Output |
|---|---|---|
| `./backup.sh` | `pg_dump -Fc` of the database through the `db` container, plus a tar of `/workspace` through the `backend` container | `backups/concierge-<UTC stamp>.dump`, `backups/concierge-<UTC stamp>.workspace.tar`; prints sizes and elapsed seconds |
| `./restore.sh <dump> [workspace.tar]` | readiness-first stop of the backend (`SIGUSR1`, then the container), `pg_restore --clean --if-exists --no-owner` into the running `db`, workspace extraction when given, `docker compose up -d backend`, wait for `/ready` 200 | prints the pg_restore time and the total **RTO** (stop → restore → ready) |

Both run from the repo root against the compose stack. `BACKUP_DIR`
overrides `./backups`; `POSTGRES_USER` / `POSTGRES_DB` follow `.env`.

`pg_restore --clean` drops and recreates every application table and every
index — the pgvector indexes on `memory_embeddings` included — so the index
build is inside the timed window. Migrations then run to head at backend
startup (a no-op when the dump is at head), the seed reconciles the static
records, and the MCP manager and the registry cache warm up against the
restored registries.

## Fresh volume

To restore onto a new host or a wiped volume: check out the repo, restore
`.env`, `./build.sh`, `./start.sh` (creates the schema on the empty volume),
then `./restore.sh backups/<dump> backups/<workspace.tar>`. The drill below
used exactly that path: a fresh `pgdata` volume, a seeded empty stack, then
the restore.

## The drill (M53) — measured

Recorded in `docs/acceptance/prod/M53/ops.md` with the full
transcript. Summary:

The numbers below are the **currently published** run — the §14p-90 drill as re-driven on the dev images, transcript in [`../acceptance/prod/M53/ops.md`](../acceptance/prod/M53/ops.md). An earlier M53-era measurement over a different data set (248 runs / 259 steps / 412 embeddings, a 2.1 MB dump, `backup.sh` 4 s, a 20 s fresh-stack boot on the destroyed volume, **RTO 10 s**) is superseded by it; both are recorded rather than averaged, because an RTO is only meaningful next to the data set it was measured on.

| Step | Measured |
|---|---|
| Data set | 120 runs, 664 run steps, 24 memories, 0 memory embeddings, 13 ambient events, 55 deliveries, 60 tools — a 2.2 MB custom-format dump plus a 12 KB workspace tarball |
| `backup.sh` | 1 s |
| `restore.sh` — `pg_restore` (schema, data, and every index, pgvector included) | 1 s |
| `restore.sh` — total RTO (stop → restore → `/ready` 200) | **9 s** |
| Same answers after restore | row counts identical on every table, all nine pgvector/HNSW indexes present, `GET /conversations/{id}` byte-identical before and after, all three MCP servers back `active`, `/ready` 200 within 1 s of start |

Note the caveat this particular data set carries: `memory_embeddings` was **0**, so the pgvector index rebuild — the part of a restore that grows fastest — was not exercised by this run. The earlier measurement (412 embeddings) is the one that did, and it is why the paragraph below stands.

Expect the RTO to scale with `run_steps` and `memory_embeddings` (the two
tables that dominate a dump); the index rebuild for pgvector is linear in
the number of embeddings and is the part that grows fastest.

## What a dump does not contain

- **Secrets and wiring** — provider keys, `REDIS_URL`, `DATABASE_URL`,
  SMTP and webhook settings: env-only by policy. Back up `.env` separately
  and treat the copy as the secret it is.
- **Native skills, prompts, code registrations** — repo/image contents,
  re-registered at startup.
- **Redis cache blobs** — disposable by contract; rebuilt read-through.
- **In-memory state** — the SSE event history and MCP client sessions do
  not survive any restart; run rows and checkpoints do (M53's stream
  synthesis resolves a reconnecting client from the row).

## Restore checks

After `restore.sh` reports ready:

```bash
curl -s http://localhost:8000/ready                 # {"status":"ready","db":"ok",...}
curl -s http://localhost:8000/api/v1/mcp-servers    # status active, recent last_connected_at
curl -s http://localhost:8000/api/v1/runs?limit=3   # the restored history
curl -s http://localhost:8000/api/v1/settings | head -c 300
```

A restored stack keeps the settings it was dumped with — including a spend
ceiling or retention gates — so review Settings once before letting ambient
work resume.
