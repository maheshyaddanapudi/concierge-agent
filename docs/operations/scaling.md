# Scaling

Honesty first: this is a POC that has now been run at **three replicas** behind one balancer (M54, `docs/acceptance/prod/M54/`) — a run created on one replica cancelled from another, a delivery reaching subscribers on every replica, consolidation once per interval cluster-wide, the load scenarios at N=3 inside the declared connection budget. Before M54 this document identified the right requirement (the run plane, the delivery plane and the clocks were per-process) and drew the wrong conclusion from it ("sticky routing makes it work"); the sections below say what is shared now, what still favours affinity, and what is not solved.

## Single-node baseline (what ships)

- Three compose services: `db` (Postgres 16), `backend` (FastAPI, **one uvicorn process, no `--workers`** — `backend/Dockerfile` CMD), `frontend` (nginx). Optional fourth: `redis` behind the `redis` compose profile.
- Runs execute as asyncio tasks **inside the single backend process** (`orchestrator/runner.py`, `RUNNING_TASKS` dict). No broker, no queue, no Celery — by design (spec §2, ADR `../adr/0001-no-broker-single-process.md`).
- Postgres is the only required stateful infrastructure: registries, runs/steps, settings, and LangGraph checkpoints all live there.
- Registry cache default is `bypass` (direct DB reads, ADR `../adr/0004-registry-cache-bypass-default.md`); `memory` is the single-node performance step.

### Connection budget (M50)

The pooled ceiling per backend replica is explicit: `DB_POOL_SIZE` (5) + `DB_MAX_OVERFLOW` (10) SQLAlchemy connections, with `DB_POOL_TIMEOUT` (30 s) the wait before a request fails. Outside that pool each replica also holds the LangGraph checkpointer pool (up to 10, psycopg), one LISTEN connection for cache invalidation, one for the ambient drain's wake channel, and the ambient leader lease session — budget **12** for those. Size Postgres `max_connections` from `replicas × (pool + overflow + 12)` plus headroom for migrations, `psql`, and the load harness. Two things that used to eat the pool no longer do: `/chat/stream` releases its session before streaming (the M49 baseline measured the pool exhausted at 15 open tabs), and `/ambient/stream` never had one. Since M51 no session is held across a provider round trip (the drain claims and commits before it processes; memory writes embed between sessions), so a burst's connection demand is bounded by its write bursts, not by provider latency.

### Admission, wall clock and shutdown (M51)

Work is bounded per replica, not discovered by exhaustion: `run_max_concurrent` (default 8) is the execution semaphore, `run_queue_max` (default 32) the number of runs that may wait in a visible `queued` status, and a chat request past both is shed with **503 + `Retry-After`** while ambient fires still queue (a fire is work already accepted). Every run has a wall clock (`run_wall_clock_s`, default 15 min) and a 30 s heartbeat; the reaper covers every run kind. On SIGTERM the process flips `GET /ready` to 503, refuses new runs, drains in-flight ones for `SHUTDOWN_GRACE_S` (default 25 s), cancels the remainder with the shutdown named in each run's error, and the next boot reaps anything still non-terminal as "orphaned by a restart" — so a rolling restart never leaves a run spinning forever. These counters are process-local (like `RUNNING_TASKS`) and exported as `concierge_runs_in_flight{state}` — the autoscaling signal per replica; the shared control plane (ownership, cancel intent, liveness) is M54, below.

### Deploy lifecycle (M53)

The order of events on one host, as `deploy.sh` runs it and as the M53 evidence recorded it:

1. **Readiness first.** `SIGUSR1` to the backend process (`docker compose kill -s USR1 backend`) calls `admission.begin_drain()`: `GET /ready` answers 503 `draining` **while the port is still open**, a new chat is a 503 with `Retry-After`, and every open stream on a run this process is *not* executing (a paused run, a run owned elsewhere) receives `event: reconnect` and closes politely; streams on runs executing here keep going to their terminal event. A balancer probing `/ready` stops routing here before anything closes — `deploy.sh` holds the 503 for `DRAIN_SETTLE_S` (3 s; set it to your probe cadence × failure threshold) before it rolls. `/health` stays 200 throughout — liveness and readiness are separate facts.
2. **SIGTERM** (the container recreate): uvicorn closes the listener, waits at most `--timeout-graceful-shutdown 5` for open connections (sse-starlette ends any remaining stream immediately), then runs the lifespan drain — in-flight runs get `SHUTDOWN_GRACE_S`, the rest are cancelled with the shutdown named; the ambient loop is **awaited**, so the leader lease is released now rather than when Postgres notices a dead session, and the next process leads within one tick. 5 s + 25 s fits under the compose `stop_grace_period` of 40 s.
3. **The new process** migrates, seeds, reaps anything left non-terminal, connects the MCP servers (with automatic reconnect for the slow ones), and answers `/ready` 200 only when the database answers too.
4. **Clients reconnect on their own** with `Last-Event-ID`. The new process has no in-memory history, so it resolves each stream from the run row — `run_status` + `done` with the recorded answer, continuing the client's sequence — and the client's sequence guard folds nothing twice. The M53 evidence (`docs/acceptance/prod/M53/`) records a roll with runs in flight on the live model: every run terminal and truthful, every stream resolved, answer text folded exactly once.

Probes: `/ready` for readiness (also 503 `degraded` when the database does not answer within 2 s), `/health` for liveness only. Compose carries the container healthcheck on `/health`, `restart: unless-stopped`, and resource limits for each service; the frontend waits for a **healthy** backend. Kubernetes maps one-to-one: readiness probe `/ready`, liveness probe `/health`, `preStop: kill -USR1 1; sleep 5`, `terminationGracePeriodSeconds: 40`.

## Multi-replica (M54): what is shared, what still favours affinity

Every fact that used to belong to "the process" now belongs to the fleet, through Postgres and one LISTEN/NOTIFY control channel — no broker, no queue (spec §2). `spec.md` §18.9 is the contract; this is the operator's view.

### Replica identity and liveness

- Each process has a `replica_id` (`REPLICA_ID`, else the container hostname) and upserts one row in `replicas` every 10 s: `heartbeat_at`, `subscribers` (its open ambient streams), `runs_in_flight`. A heartbeat older than **45 s** means dead.
- `GET /replicas` lists the fleet with `live` per row, this process's id, whether its control listener is connected, and the connection-budget arithmetic. `concierge_replica_info{replica}` is on `/metrics`; `concierge_loop_errors_total{loop="replica"}` counts a heartbeat that failed.
- Shutdown retires the row (the M53 drain awaits the heartbeat loop); a crash lapses it on the cutoff.

### The run plane

- **Ownership.** `runs.owner_replica` is stamped at creation — the creating process runs the task. `GET /runs/{id}` shows it.
- **Cancel from anywhere.** `POST /runs/{id}/cancel` on the owner cancels the task as before. On any other replica it is a **persisted intent**: `cancel_requested_at` is set, a `cancel` message goes out on `concierge_control`, and the owner cancels at once (its 30 s heartbeat re-reads the intent as the fallback for a lost NOTIFY). The response is the row's real status — `200 cancelled` if the owner acted within ~3 s, `202 cancel_requested` otherwise. Nothing ever writes `cancelled` on a run it cannot stop (the pre-M54 false cancel that resurrected as `completed`).
- **Reaping.** Boot-time reaping (`orphaned by a restart`) is scoped to the booting replica's own rows; runs whose owner is dead are failed on any replica by the periodic loop with `owner replica gone: <id>`; the M51 heartbeat reaper is unchanged.
- **Streams.** A chat stream that lands on a replica not executing the run gets no intermediate events (the event bus is still per process — token fan-out across replicas is not built) but **does resolve**: the owner announces every terminal transition on the control channel, the holding replica wakes (or re-reads the row at its next 15 s beat) and serves the recorded terminal events (`run_status` + `done` with the answer, sequence continued). So affinity is *recommended* for chat — the user sees tokens stream only when the stream lands on the owner — and *never required* for correctness. Under compose the frontend's nginx round-robins; a `POST /chat` and its `GET /chat/stream` are two requests and can land on different replicas. Put a cookie-affine balancer in front for the streaming experience; the answer arrives either way.
- **HITL resume** (`POST /runs/{id}/hitl`) still executes on the replica that receives it (the checkpoint is shared) — that replica becomes the owner of the resumed task.

### The delivery plane

- The leader's flush publishes each in-app delivery on the control channel; every replica re-fans it to its own `/ambient/stream` subscribers, ignoring its own origin. A toast reaches the whole audience wherever the leader is.
- The pursuit oracle (§18.4) is the **cluster audience** — this replica's subscribers plus the fresh `subscribers` count of every other live replica — so `ambient_pursuit: away` no longer emails people watching a tab on a non-leader replica, and the salience learner is no longer trained on a topology artefact.

### Clocks and boot

- The consolidation jobs and retention keep `last_run_at` in `job_clock`: once per interval cluster-wide, whichever replica leads; a restart re-runs nothing (compaction included). Advisory locks still guard concurrency; the clock guards scheduling.
- Migrations and seeding run under a session advisory lock (classid 427019): N replicas booting together apply the schema once. Start them together freely.

### The connection budget

Per replica: `DB_POOL_SIZE + DB_MAX_OVERFLOW` pooled, the LangGraph checkpointer pool (10), and **4 session connections that cannot go through a transaction-mode pooler** — the registry-cache LISTEN, the ambient wake LISTEN, the control listener, the leader lease. With a 10-connection reserve for migrations, `psql` and the load harness:

```
needed = DB_REPLICAS × (pool + overflow + 10 + 4) + 10
       = 3 × (5 + 10 + 10 + 4) + 10 = 97   ≤ DB_MAX_CONNECTIONS (100)
```

Declare the fleet with `DB_REPLICAS` and `DB_MAX_CONNECTIONS`; the arithmetic is logged at boot (`db_connection_budget`, a warning when it does not fit) and served by `GET /replicas` (`budget.max_replicas_at_declared` is the fleet size the declared Postgres seats). Beyond that, raise `max_connections` (each connection is ~10 MB of Postgres RAM) or put a pooler in front of the **pooled** connections only: `DB_STATEMENT_CACHE_SIZE=0` (the default) keeps them free of prepared statements so a transaction-mode pgbouncer works; the four session connections must bypass it. The M54 evidence records `pg_stat_activity` under the N=3 load scenarios against this arithmetic.

### The rate limiter

With auth on, the §18.8 token bucket lives in `rate_buckets` — one budget across replicas instead of N. One short transaction per request; keys idle for an hour are evicted by the periodic loop, so the key space is bounded even when the key is a client address an attacker controls. A database failure fails open with a log (M51 admission already bounds the work).

### Cache coherency

`registry_cache_mode: memory` is a per-process cache kept coherent by LISTEN/NOTIFY. Two races the review found — an invalidation landing *during* a reload being discarded, and a slow read-through resurrecting a deleted redis blob — are closed: a reload discards the dirty flag (and writes the redis blob) only if the generation it started from is unchanged, every entry expires on `REGISTRY_CACHE_TTL_S` (300 s) whatever happens, and `GET /cache/status` reports `dirty` beside `generation`. Verify at N>1 exactly as before: a write on replica A bumps `generation` on B and C, and `dirty` returns to `false` on their next read.

### MCP under N replicas

Every replica holds its own connection to every server (a tool call is served wherever the run executes), so N replicas mean N stdio subprocesses per server — budget memory for it. Ingest is idempotent (`ON CONFLICT` on `(server, tool name)` under a per-server advisory lock), so a concurrent cold boot produces every tool exactly once, and each replica reconciles its subprocess set against the registry on every health tick: a server registered or deleted through any replica is connected or torn down everywhere within `mcp_health_interval_s`.

### Memory at scale

Embeddings live in one typed column per supported dimension (`emb_64` … `emb_3072`, `halfvec` above 2000), each with a real HNSW cosine index — the untyped column the first schema carried could not be indexed and recall latency grew with the corpus. The M54 evidence records recall p50/p95 at 10k, 100k and 1M embeddings with `EXPLAIN` showing the index scan. A model whose dimension has no column degrades to lexical-only with a warning; adding a dimension is one migration (`alembic/versions/s8g9h0i1j2k3_m54_scale.py` is the template).

The periodic sweeps that touch every memory row — decay and the contradiction sweep — are **one set-based `UPDATE` each** (`app/memory/lifecycle.py`). The first version of the §14q-95 drill seeded a million memories and the row-by-row decay sweep loaded them all as ORM objects into a replica with a 1.5 GB limit; the kernel killed it, compose restarted it, and it died again on the next boot tick — 2,693 restarts before the setting was switched off at the database. The rewrite keeps the formula (`importance · 2^(−age/half_life)`, a row's own half-life first) and the ranking rule (newest validity per `(scope, entity_key)` stays) and materialises nothing; the M54 suite runs both over 20k / 9k seeded rows and asserts the source carries no `select(Memory)`. Reflection and communities are bounded by their own windows (`_REFLECTION_WINDOW`, `_SUMMARY_MEMORY_CAP`); the embedding backfill takes 500 rows per tick.

### The edge

- `docker compose up --scale backend=3` binds each replica to a host port from `BACKEND_PORT_RANGE` (8000, 8001, 8002); the frontend's nginx resolves `backend` per request through Docker's DNS (`resolver 127.0.0.11`), so replicas join and leave without a restart and requests round-robin.
- Prometheus discovers each replica as its own target (`dns_sd_configs` in `docs/observability/prometheus.yml`); a scrape through the frontend VIP would alternate replicas and show counter resets.
- **Deploys at N>1**: compose recreates every replica of a service together — `deploy.sh` at N=3 is a brief full outage, not a rolling roll. A rolling deploy is an orchestrator's job: on Kubernetes map `/ready`, `/health`, `preStop: kill -USR1 1; sleep 5` and `terminationGracePeriodSeconds: 40` as the M53 section says and let the rollout strategy roll one pod at a time; every M54 property (ownership, intents, fan-out, clocks) holds across the roll because none of it lives in a process.

### Cache promotion: memory → redis

The `redis` backend exists so multiple replicas can share one cache instead of N private ones. Promotion path:

1. **Provision**: `./quick-setup.sh --redis` writes `REDIS_URL=redis://redis:6379/0` and `COMPOSE_PROFILES=redis` to `.env`; the next `./start.sh` includes the `redis:7-alpine` service (or run `docker compose --profile redis up -d`). For an external Redis, just set `REDIS_URL` — it is env-only by design (credentials never in DB/UI).
2. **Restart the backend** if `REDIS_URL` changed (env vars are read at process start).
3. **Flip the setting**: Settings → Registry cache → `redis`, or `PATCH /settings {"registry_cache_mode": "redis"}`. The save is **ping-validated** (`settings_store._ping_redis`): unreachable Redis → 422, mode unchanged. Missing `REDIS_URL` → 422 before the ping.
4. **Verify**: `GET /cache/status` reports `mode: redis`; reads are read-through blobs (`concierge:cache:<registry>` keys, each with the TTL), invalidation is delete-on-invalidate.
5. **Rollback lever**: flip back to `bypass` at any time — instant escape hatch, byte-identical pre-cache semantics.

Note the redis backend still keeps per-process generation counters and pairs with the LISTEN/NOTIFY channel for dirty marking; Redis holds the data blobs, Postgres carries the invalidation signal.

### Retrieval at scale

When registries grow past what full prompt injection tolerates:

- **Enable**: `PATCH /settings {"retrieval_enabled": true}`. Per registry it activates only above `retrieval_threshold` records (default 30); below that, full injection, bit-for-bit. `retrieval_top_k` (default 10) is the truncation size.
- **Scoring** (`backend/app/retrieval.py`) runs in-process over the cache snapshot — never a per-call DB query: BM25 over name+description, fused (reciprocal-rank, k=60) with cosine over stored embeddings when an `embedding_model` is configured. No embedding model → lexical-only, silently.
- **Safety valves**: plan-referenced and already-used ids are pinned past ranking; full-catalog fallback bypasses retrieval entirely; every truncation logs its drop count and the injected catalog carries a "showing N of M" footer.
- **JSONB → pgvector swap path** (registry embeddings, not memory): embeddings are stored today as plain `jsonb` float arrays with an `embedding_hash` (migration `f31a9c04e7d1`; see `../architecture/data-model.md`), and cosine runs in Python over the cache snapshot — deliberately, so the registry stays small and fast. When catalogs outgrow in-memory ranking, the documented swap (spec §7.3) is a typed `vector` column with an index — the memory side-table (above) is the worked example. The full decision record is [ADR-0006](../adr/0006-jsonb-embeddings-before-pgvector.md).

## Explicitly NOT solved

- **No authentication or authorization** — every endpoint is open; the UI is an unauthenticated admin surface. Out of scope by declaration (README "Scope notes"); the seam it plugs into is M55.
- **No multi-tenancy** — one set of registries, conversations, and settings per deployment.
- **Token streams do not follow the user across replicas** — the run event bus is per process; a stream on a non-owner replica resolves from the record (the answer arrives) but shows no intermediate events. Affinity for the chat plane is recommended, not required.
- **No horizontal run migration** — a running task cannot move to another replica; a dead owner's run is failed truthfully and can be retried.
- **Rolling deploys at N>1 are the orchestrator's job** — compose recreates all replicas of a service together.
- **Load-tested at N=3 on one host** — the M54 numbers are a single Docker host with three backend containers, not three machines; network partitions between replicas and Postgres were not injected.
