# Scaling

Honesty first: this is a POC. The scale-out path below is **designed in but not load-tested** — the multi-replica machinery (LISTEN/NOTIFY invalidation, Redis cache backend) exists in code and is dormant on a single node; nobody has run this stack behind a load balancer under production traffic. Treat this document as the map of what is prepared, what to verify, and what is missing.

## Single-node baseline (what ships)

- Three compose services: `db` (Postgres 16), `backend` (FastAPI, **one uvicorn process, no `--workers`** — `backend/Dockerfile` CMD), `frontend` (nginx). Optional fourth: `redis` behind the `redis` compose profile.
- Runs execute as asyncio tasks **inside the single backend process** (`orchestrator/runner.py`, `RUNNING_TASKS` dict). No broker, no queue, no Celery — by design (spec §2, ADR `../adr/0001-no-broker-single-process.md`).
- Postgres is the only required stateful infrastructure: registries, runs/steps, settings, and LangGraph checkpoints all live there.
- Registry cache default is `bypass` (direct DB reads, ADR `../adr/0004-registry-cache-bypass-default.md`); `memory` is the single-node performance step.

### Connection budget (M50)

The pooled ceiling per backend replica is explicit: `DB_POOL_SIZE` (5) + `DB_MAX_OVERFLOW` (10) SQLAlchemy connections, with `DB_POOL_TIMEOUT` (30 s) the wait before a request fails. Outside that pool each replica also holds the LangGraph checkpointer pool (up to 10, psycopg), one LISTEN connection for cache invalidation, one for the ambient drain's wake channel, and the ambient leader lease session — budget **12** for those. Size Postgres `max_connections` from `replicas × (pool + overflow + 12)` plus headroom for migrations, `psql`, and the load harness. Two things that used to eat the pool no longer do: `/chat/stream` releases its session before streaming (the M49 baseline measured the pool exhausted at 15 open tabs), and `/ambient/stream` never had one. Since M51 no session is held across a provider round trip (the drain claims and commits before it processes; memory writes embed between sessions), so a burst's connection demand is bounded by its write bursts, not by provider latency.

### Admission, wall clock and shutdown (M51)

Work is bounded per replica, not discovered by exhaustion: `run_max_concurrent` (default 8) is the execution semaphore, `run_queue_max` (default 32) the number of runs that may wait in a visible `queued` status, and a chat request past both is shed with **503 + `Retry-After`** while ambient fires still queue (a fire is work already accepted). Every run has a wall clock (`run_wall_clock_s`, default 15 min) and a 30 s heartbeat; the reaper covers every run kind. On SIGTERM the process flips `GET /ready` to 503, refuses new runs, drains in-flight ones for `SHUTDOWN_GRACE_S` (default 25 s), cancels the remainder with the shutdown named in each run's error, and the next boot reaps anything still non-terminal as "orphaned by a restart" — so a rolling restart never leaves a run spinning forever. These counters are process-local (like `RUNNING_TASKS`) and exported as `concierge_runs_in_flight{state}` — the autoscaling signal; a shared control plane is M54.

### Deploy lifecycle (M53)

The order of events on one host, as `deploy.sh` runs it and as the M53 evidence recorded it:

1. **Readiness first.** `SIGUSR1` to the backend process (`docker compose kill -s USR1 backend`) calls `admission.begin_drain()`: `GET /ready` answers 503 `draining` **while the port is still open**, a new chat is a 503 with `Retry-After`, and every open stream on a run this process is *not* executing (a paused run, a run owned elsewhere) receives `event: reconnect` and closes politely; streams on runs executing here keep going to their terminal event. A balancer probing `/ready` stops routing here before anything closes — `deploy.sh` holds the 503 for `DRAIN_SETTLE_S` (3 s; set it to your probe cadence × failure threshold) before it rolls. `/health` stays 200 throughout — liveness and readiness are separate facts.
2. **SIGTERM** (the container recreate): uvicorn closes the listener, waits at most `--timeout-graceful-shutdown 5` for open connections (sse-starlette ends any remaining stream immediately), then runs the lifespan drain — in-flight runs get `SHUTDOWN_GRACE_S`, the rest are cancelled with the shutdown named; the ambient loop is **awaited**, so the leader lease is released now rather than when Postgres notices a dead session, and the next process leads within one tick. 5 s + 25 s fits under the compose `stop_grace_period` of 40 s.
3. **The new process** migrates, seeds, reaps anything left non-terminal, connects the MCP servers (with automatic reconnect for the slow ones), and answers `/ready` 200 only when the database answers too.
4. **Clients reconnect on their own** with `Last-Event-ID`. The new process has no in-memory history, so it resolves each stream from the run row — `run_status` + `done` with the recorded answer, continuing the client's sequence — and the client's sequence guard folds nothing twice. The M53 evidence (`docs/acceptance/prod/M53/`) records a roll with runs in flight on the live model: every run terminal and truthful, every stream resolved, answer text folded exactly once.

Probes: `/ready` for readiness (also 503 `degraded` when the database does not answer within 2 s), `/health` for liveness only. Compose carries the container healthcheck on `/health`, `restart: unless-stopped`, and resource limits for each service; the frontend waits for a **healthy** backend. Kubernetes maps one-to-one: readiness probe `/ready`, liveness probe `/health`, `preStop: kill -USR1 1; sleep 5`, `terminationGracePeriodSeconds: 40`.

## Multi-replica: what is ready, what is not

### Cross-replica cache invalidation (ready, dormant)

Implemented in `backend/app/registry_cache.py`:

- **Mechanism**: every `invalidate(registry)` (a) marks the local cache dirty with relationship propagation (tools → skills → sub_agents), then (b) fires `SELECT pg_notify('registry_cache_inv', '<origin>:<registry>')`. Each process holds a dedicated asyncpg connection LISTENing on that channel (`start_listener`, called at startup) and marks its local cache dirty when a peer broadcasts.
- **Origin filtering**: each process generates a random `origin` id at construction; notifications carrying its own origin are ignored, so invalidation loops are impossible by construction. The LISTEN callback calls `_mark_dirty` (local only, no re-notify) for the same reason.
- **Best-effort semantics**: both the notify and the listener are wrapped in catch-log (`cache_notify_failed`, `cache_listener_unavailable`). Single-replica correctness never depends on the notify path — the writing process already marked itself dirty. Across replicas, a lost notification means a peer serves stale registry data until its next invalidation; there is no retry, no queue, no catch-up replay.
- **What to verify when enabling multiple replicas**:
  1. Each replica logs `cache_listener_started` with a distinct `origin` at startup.
  2. A registry write on replica A (e.g. toggle a tool's `direct_exposure`) bumps the `generation` counter in `GET /cache/status` on replica B without a manual refresh.
  3. No `cache_listener_unavailable` / `cache_notify_failed` warnings under steady state (poolers like pgbouncer in transaction mode break LISTEN/NOTIFY — the listener needs a real session-level connection).
  4. In `memory` mode, confirm the mid-run visibility test from spec §11 (expose a tool mid-run → next model call sees it) across replicas, not just within one.

### SSE and run execution: sticky is mandatory

Reasoned from code, not from hope:

- SSE replay is **in-memory**: `RunEventBus` (`orchestrator/context.py`) keeps per-run event history in a process-local dict. `GET /chat/stream/{run_id}` (`api/chat.py`) replays that history, then tails a per-subscriber asyncio queue. Nothing about the event stream is DB-backed (run *steps* are persisted for traces, but the SSE event sequence — `token`, `thinking`, `activity`, `hitl_request`, `done` — is not).
- The run itself executes as an asyncio task in whichever process handled `POST /chat`. Events are emitted only into that process's bus.
- Therefore, with N replicas today: the SSE stream **must** land on the replica that owns the run — and so must `POST /runs/{id}/cancel` (it looks up `RUNNING_TASKS` in process memory) and `POST /runs/{id}/hitl` resume (any replica *could* resume from the shared Postgres checkpoint, but the resumed task's events would then stream from the resuming replica, stranding an open stream elsewhere).
- Practical requirement: session-affinity routing keyed so that a conversation's chat POST, its stream GET, and its control POSTs hit the same replica. What multi-replica would additionally require to drop stickiness: moving the event bus out of process memory (e.g. Postgres LISTEN/NOTIFY or Redis pub/sub for events, plus DB-backed event history for replay) and a run-ownership/handoff story for cancel. **None of that exists today** — do not put a round-robin balancer in front of multiple backends and expect chat to work.
- Related single-node caveat: a backend restart loses all SSE history; old runs' traces remain in the DB. Since M53 a reconnecting client still resolves — the new process synthesizes the terminal events from the run row — but intermediate events (`plan`, `route`, `activity`, tokens) are not replayed.
- **HTTP/2 at the edge** (M53): browsers cap HTTP/1.1 at six connections per host, and every open chat stream, the ambient stream and the polling share that budget — three or four tabs with live runs is where a fresh install runs out. HTTP/2 multiplexes them over one connection, but browsers only speak it over TLS, so it is a property of the TLS terminator in front of the frontend container; `frontend/nginx.conf` carries a commented `listen 443 ssl; http2 on;` server block for the case where nginx itself is that terminator.

### Cache promotion: memory → redis

The `redis` backend exists so multiple replicas can share one cache instead of N private ones. Promotion path:

1. **Provision**: `./quick-setup.sh --redis` writes `REDIS_URL=redis://redis:6379/0` and `COMPOSE_PROFILES=redis` to `.env`; the next `./start.sh` includes the `redis:7-alpine` service (or run `docker compose --profile redis up -d`). For an external Redis, just set `REDIS_URL` — it is env-only by design (credentials never in DB/UI).
2. **Restart the backend** if `REDIS_URL` changed (env vars are read at process start).
3. **Flip the setting**: Settings → Registry cache → `redis`, or `PATCH /settings {"registry_cache_mode": "redis"}`. The save is **ping-validated** (`settings_store._ping_redis`): unreachable Redis → 422, mode unchanged. Missing `REDIS_URL` → 422 before the ping.
4. **Verify**: `GET /cache/status` reports `mode: redis`; reads are read-through blobs (`concierge:cache:<registry>` keys), invalidation is delete-on-invalidate.
5. **Rollback lever**: flip back to `bypass` at any time — instant escape hatch, byte-identical pre-cache semantics.

Note the redis backend still keeps per-process generation counters and pairs with the LISTEN/NOTIFY channel for dirty marking; Redis holds the data blobs, Postgres carries the invalidation signal.

### Retrieval at scale

When registries grow past what full prompt injection tolerates:

- **Enable**: `PATCH /settings {"retrieval_enabled": true}`. Per registry it activates only above `retrieval_threshold` records (default 30); below that, full injection, bit-for-bit. `retrieval_top_k` (default 10) is the truncation size.
- **Scoring** (`backend/app/retrieval.py`) runs in-process over the cache snapshot — never a per-call DB query: BM25 over name+description, fused (reciprocal-rank, k=60) with cosine over stored embeddings when an `embedding_model` is configured. No embedding model → lexical-only, silently.
- **Safety valves**: plan-referenced and already-used ids are pinned past ranking; full-catalog fallback bypasses retrieval entirely; every truncation logs its drop count and the injected catalog carries a "showing N of M" footer.
- **JSONB → pgvector swap path**: embeddings are stored today as plain `jsonb` float arrays with an `embedding_hash` (migration `f31a9c04e7d1`; see `../architecture/data-model.md`), and cosine runs in Python over the cache snapshot — deliberately, so the stock `postgres:16` image keeps working. When catalogs outgrow in-memory ranking, the documented swap (spec §7.3) is: pgvector-enabled Postgres image + a migration changing `embedding` to a `vector` column with an index, and moving the cosine/top-K step into SQL. The port surface (`get_embeddings("provider:model", texts)`) and the write-path/backfill embedding maintenance are unchanged by that swap. The full decision record is [ADR-0006](../adr/0006-jsonb-embeddings-before-pgvector.md); spec §7.3/§7.4 and the data-model doc carry the implementation detail.

## Explicitly NOT solved

- **No authentication or authorization** — every endpoint is open; the UI is an unauthenticated admin surface. Out of scope by declaration (README "Scope notes").
- **No multi-tenancy** — one set of registries, conversations, and settings per deployment.
- **Single-writer / single-process assumptions**: run execution, cancel (`RUNNING_TASKS`), SSE event bus, and the compiled-graph cache are process-local. The seed loader and Alembic migrations run at every backend startup and are idempotent for one process; concurrent first-boot of multiple replicas racing migrations/seeds has not been exercised — start one replica first.
- **No horizontal run distribution** — there is no mechanism to move or resume a live run on another replica (HITL-paused runs are the exception: they restart from the Postgres checkpoint wherever the resume lands, subject to the SSE caveat above).
- **No load testing** — every claim above is architectural, not empirical.
