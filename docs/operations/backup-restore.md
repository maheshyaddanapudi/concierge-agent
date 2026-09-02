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

Recorded in `docs/acceptance/prod/M53/restore-drill.md` with the full
transcript. Summary:

| Step | Measured |
|---|---|
| Data set | 248 runs, 259 run steps, 412 memory embeddings (pgvector), 151 ambient events, 185 deliveries, 29 tools — a 2.1 MB custom-format dump plus a 12 KB workspace tarball |
| `backup.sh` | 4 s |
| Fresh stack on the destroyed volume (migrations + seeds, `/ready` 200) | 20 s — with 0 runs and a 404 for the reference conversation |
| `restore.sh` — `pg_restore` (schema, data, indexes incl. pgvector) | 1 s |
| `restore.sh` — total RTO (stop → restore → `/ready` 200) | **10 s** |
| Same answers after restore | row counts identical on every table, both pgvector indexes present, `GET /conversations/{id}` byte-identical before and after (2 messages), both seeded MCP servers active |

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
