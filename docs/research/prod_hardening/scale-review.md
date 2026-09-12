# Horizontal-scale, performance, and deployment-readiness review

**Branch**: `prod_hardening` (at `c8fcba8`)
**Question**: not "what does the code do wrong" — that is answered in [`architecture-review.md`](./architecture-review.md) and [`code-review.md`](./code-review.md). This report asks: **what does a horizontally-scaled production deployment of this system need that is not here at all?**

**Target deployment reviewed against**: N backend replicas behind a load balancer (optionally with session affinity), one Postgres, optional Redis, rolling deploys, a real user population. The workload is I/O-bound on provider calls; the unit of work (a run) lasts seconds to minutes and can pause for hours awaiting a human.

**Out of scope by explicit decision**: authentication, authorization, RBAC. Where a per-process rate limiter breaks at N>1 it is reported as a scaling property, not an access-control one.

**Prior findings are cited, never re-argued**: `arch-C1`, `code-H4`, etc. refer to the two reviews above.

**Method**: verified at the enforcement site. `spec.md` states intent and has drifted before; where the code and the spec disagree the code is the finding. Arithmetic is shown for every asserted ceiling.

---

## Summary

The system is *closer* to multi-replica than the prior reviews imply, and that is the danger. `docs/operations/scaling.md` is an unusually honest document — it correctly identifies that SSE and run execution require session affinity, and correctly says "no load testing — every claim above is architectural, not empirical." But it draws the wrong conclusion from its own analysis: it presents **sticky routing as the sufficient condition** for N>1. It is not. Three whole planes of the system are unreachable by any routing decision a load balancer can make, because their work is not initiated by an HTTP request at all.

The gaps cluster into four kinds:

1. **Ceilings that do not move when you add replicas.** The ambient plane is single-leader by design and serial within the tick; the delivery/toast plane collapses to 1/N reach; memory recall is an un-indexable exact KNN scan; Postgres connections cap the fleet at 3 replicas and the standard escape hatch (a pooler) does not currently work with this driver configuration.
2. **The deployment shape is untested against a real proxy.** The chat SSE heartbeat is 120 s — longer than the default idle timeout of every common load balancer — and the stream carries no `id:` field, so the browser's automatic reconnect replays the full history into an accumulator and **visibly doubles the answer text**. This breaks at N=1 behind an ALB; N replicas merely make it worse.
3. **No lifecycle story.** No readiness endpoint, no graceful-shutdown budget, no drain, no `stop_grace_period`, no expand/contract discipline, no CI. A rolling deploy is currently indistinguishable from a fleet-wide `kill -9`.
4. **No performance engineering exists at all.** No load test, no capacity model, no latency budget, no SLI definitions, no cost model, no autoscaling signal, and metrics that cannot even be scraped correctly from N replicas behind one VIP.

### What genuinely scales fine

Stated plainly, because a review that finds everything broken is useless:

- **The `FOR UPDATE SKIP LOCKED` drain is correctly replica-parallel.** `backend/app/ambient/drain.py:65-107` claims rows with SKIP LOCKED and every replica runs it (`drain.py:216-218`). Ambient *event processing* genuinely gets faster with replicas. (Its transaction scope is `arch-H8`/`code-H3` — a different problem.)
- **The leader-lease mechanics are right.** `backend/app/ambient/coordinate.py` — the session *is* the lease, so process death releases the lock server-side with no clock comparison and no lease table. What the lease *measures* is `arch-H6`; the mechanism itself needs no change.
- **HITL state is genuinely shared.** LangGraph checkpoints live in Postgres (`backend/app/db.py:43-62`), so a `paused_hitl` run can resume on any replica. This is the one piece of run state that is already replica-portable.
- **The checkpointer pool is already pooler-safe.** `backend/app/db.py:57` sets `prepare_threshold: 0` — exactly what pgbouncer transaction mode requires. Somebody thought about this. (The SQLAlchemy engine did not; see B2.)
- **Presence is DB-backed.** `UserPresence` rows (`backend/app/ambient/presence.py:34-49`) are written by whichever replica serves the heartbeat and read by the leader. Correct by construction.
- **The `ambient_runs_per_day` cap is a DB count, not an in-memory counter** (`backend/app/ambient/decide.py:60-72`). Mildly racy across concurrent drains, but it does not silently become N× the configured cap the way the HTTP rate limiter does.
- **Registry-cache invalidation is loop-free by construction.** The origin-id filter (`backend/app/registry_cache.py:285-292`) and the local-only `_mark_dirty` in the listener callback are the right design. Its *races* are H5 below; its *topology* is sound.
- **Registry embeddings as JSONB ranked in-process** (`backend/app/retrieval.py`) is the correct call at registry scale (hundreds of records) and explicitly ADR'd. Do not "fix" this.
- **Stateless registry projections** (`backend/app/orchestrator/middleware.py:1-16`) mean registry reads need no affinity at all.
- **A2A adopt-or-send keyed on `(run_id, call_key)`** (`backend/app/a2a/proxy.py:91`) is replica-safe idempotency, already correct.

---

## Scaling ceilings

| What does not scale | Why | Practical limit | What it would take to lift |
|---|---|---|---|
| **Postgres connections** | 28 connections per replica at saturation (15 SQLAlchemy + 10 checkpointer + 3 session-scoped asyncpg) against stock `max_connections=100` | **3 replicas.** N=4 → 112 > 97 usable → `FATAL: sorry, too many clients already` | Size the pools from config; raise `max_connections`; add pgbouncer — but see B2, the driver is not configured for it |
| **Ambient evaluators** (schedules, polls, state conditions, deliveries, salience, learner, anticipation, A2A poller) | Leader-only by design (`drain.py:166-214`, spec §18.9) and one serial `await` chain inside the tick | **1 replica's worth, forever.** Adding replicas adds exactly zero ambient throughput | Shard the evaluator set by hash of routine/intent id across K advisory locks, or make each evaluator a claim-based queue over its own table |
| **In-app delivery reach (toasts)** | `_publish` fans out to the *publishing process's* subscriber dict (`channels.py:136,164`), and only the leader ever publishes | **1/N of connected users** receive any toast | Move the delivery broadcast to `pg_notify` on a `deliveries` channel that every replica LISTENs on and re-fans to its local subscribers |
| **Pursuit / presence oracle** | `stream_subscriber_count()` counts only the leader's subscribers (`channels.py:155,254`) | External escalation (email/webhook) decided on 1/N of the truth | Same fix; count subscribers via a shared registry (a `sse_subscribers` heartbeat table, or Redis `SCARD`) |
| **Memory semantic recall** | `memory_embeddings.embedding` is `Vector(None)` (`models/memory.py:110`) — pgvector cannot build ivfflat or hnsw on an unconstrained-dimension column, so `ORDER BY e.embedding <=> …` (`rank.py:145`) is always an exact KNN sequential scan | ~620 MB of vector heap scanned per recall at 100 k memories; ~6.2 GB at 1 M. N replicas issue N× concurrent scans against one DB | Materialize one dimension-typed partial column (or one table) per active `model_key`, index it hnsw, and keep `Vector(None)` only as the migration staging column |
| **Consolidation jobs** | One advisory lock per job class (`memory/scheduler.py:81-91`) — correct for exclusivity, but it means one replica does all consolidation | 1 replica's worth of decay/reflection/compaction/communities | Partition each sweep by a hash range and take one lock per shard |
| **Alembic + seed + embedding backfill at boot** | Every replica runs all three, unlocked (`main.py:31-35,67`) | N× work, N× embedding spend, and a race at cold boot | Advisory-lock the whole boot block (`arch-M2`), or move it to an init job |
| **Browser connections per origin** | nginx is `listen 80;` with no `http2` (`frontend/nginx.conf:2`); HTTP/1.1 caps browsers at 6 connections per origin, and the app holds 2 persistent SSE per tab | **3 tabs** — the 4th tab's XHRs queue indefinitely and the UI appears frozen | `http2 on;` (one line) plus TLS termination |
| **Postgres itself** | Every read path is un-cached by default (`registry_cache_mode: bypass`, `arch-H5`), so replica count multiplies DB round-trips rather than reducing them | Throughput becomes a function of `app_settings` latency at any N | Make `memory` the default (`arch-H5`), then the ceiling moves to the connection budget |

### Connection-budget arithmetic

Per backend replica, at saturation:

| Consumer | Count | Evidence |
|---|---|---|
| SQLAlchemy async engine | 5 pool + 10 overflow = **15** | `backend/app/db.py:22` — `create_async_engine(url, pool_pre_ping=True)`, no sizing → SQLAlchemy defaults |
| LangGraph checkpointer (psycopg pool) | `max_size=10` (min 4 held from boot) | `backend/app/db.py:53-57` |
| Ambient leader lease (asyncpg, session-scoped) | **1** | `backend/app/ambient/coordinate.py:56` |
| Ambient `LISTEN` (asyncpg, session-scoped) | **1** | `backend/app/ambient/drain.py:142` |
| Registry-cache `LISTEN` (asyncpg, session-scoped) | **1** | `backend/app/registry_cache.py:283` |
| **Total** | **28** | |

`pgvector/pgvector:0.8.6-pg16` ships stock `max_connections = 100`, `superuser_reserved_connections = 3` → **97 usable**.

- N=3 → 84 ✓
- N=4 → 112 ✗

**The fleet caps at three replicas**, and the third one is already at 87 % of the connection budget with no headroom for `psql`, a migration runner, or a monitoring agent.

---

# Findings

## Blocker for horizontal scale

### B1 — The in-app delivery plane reaches only the leader replica's subscribers, and the pursuit oracle escalates on 1/N of the truth

**Evidence**

- `backend/app/ambient/channels.py:136` — `_subscribers: dict[int, asyncio.Queue] = {}` is a module-level, per-process dict.
- `backend/app/ambient/channels.py:164-186` — `_publish` iterates `_subscribers.values()`, i.e. only the SSE clients attached to *this* process.
- `backend/app/ambient/channels.py:246-255` — `dispatch_delivered` samples `watchers = stream_subscriber_count()` and then calls `_publish`.
- `backend/app/ambient/deliver.py:297, 338, 374` — `dispatch_delivered` is called **only** from `_digest_flush`, `_flush_tier1` and `_flush_bucket`, all of which are reached only via `flush_deliveries`.
- `backend/app/ambient/drain.py:190` — `flush_deliveries()` is inside the `if leader:` branch. **Only the leader ever publishes.**
- `backend/app/ambient/channels.py:206-244` — `_record_in_app_outcome` writes an "unseen" marker when `watchers == 0`, and `_pursue(pursuit, watchers)` gates the *external* half (email, webhook) on the same count.
- `backend/app/ambient/salience.py:341-360` — the M42 salience pass re-judges deliveries where `seen_at IS NULL`, and feeds the salience tuner.

**Failure scenario at N replicas.** Three replicas, ten users, load-balanced. Replica 1 holds the lease. A tier-0 interrupt flushes. `_publish` reaches the ~3 users whose `/ambient/stream` happens to terminate on replica 1; the other ~7 see nothing — no toast, ever. Worse, the two follow-on consumers are now reading a corrupted signal:

- With `ambient_pursuit: "away"`, `watchers` is a third of the real audience, so the system emails users who are demonstrably sitting in front of an open tab.
- With `ambient_salience_mode` on, ~2/3 of real-time deliveries are marked unseen and fed to the re-judge pass and the tuner, which then *learns* that its tier assignments are too quiet and escalates further. The learning loop is being trained on an artifact of the topology.

**On the spec's defence.** `spec.md:1289-1293` argues this is correct: "the hub is per-process, so a tick on replica A can only ever toast A's subscribers, and A's count is exactly what A delivered to." The premise is true and the conclusion does not follow. It establishes that the *oracle* is self-consistent, while quietly conceding that A is the only replica that ever delivers. Self-consistency about a 1/N sample is not correctness. **This is the one place where the spec's own reasoning is wrong, not merely drifted.**

**Sticky sessions cannot fix this.** The leader is *elected*, not chosen by a client. No routing rule can make an arbitrary user's SSE connection land on whichever replica happens to hold an advisory lock this minute — and the leader changes on every deploy and every crash.

**Remediation** (medium). Replace the direct `_publish` call with a `pg_notify('ambient_delivery', <payload>)`; every replica already runs a LISTEN loop (`drain.py:135-147`) and can re-fan to its local `_subscribers`. For the oracle, have each replica upsert `(replica_id, subscriber_count, heartbeat_at)` into a small table on each tick and have `dispatch_delivered` sum the fresh rows. Both are Postgres-only and respect the §2 no-broker constraint.

---

### B2 — The connection budget caps the fleet at three replicas, and the standard escape hatch (a pooler) does not work with this driver configuration

**Evidence**

- Arithmetic above: 28 connections/replica vs 97 usable → 3 replicas.
- **The three session-scoped asyncpg connections cannot go through a transaction-mode pooler at all.** `LISTEN`/`NOTIFY` (`drain.py:144`, `registry_cache.py:293`) and `pg_try_advisory_lock` held across statements (`coordinate.py:57-63`) both require a stable session. `docs/operations/scaling.md:24` already knows this ("poolers like pgbouncer in transaction mode break LISTEN/NOTIFY") but treats it as a verification note rather than an architectural constraint.
- **The SQLAlchemy engine is not pooler-compatible either.** `backend/app/db.py:22` passes no `connect_args`. `grep -rn "connect_args\|statement_cache" backend/app/` returns nothing. asyncpg uses server-side prepared statements by default; under pgbouncer transaction pooling this produces `DuplicatePreparedStatementError` as soon as two clients share a server connection. Fixing it needs `connect_args={"statement_cache_size": 0, "prepared_statement_name_func": …}` — a code change that does not exist.
- Contrast `backend/app/db.py:57` — the checkpointer pool *does* set `prepare_threshold: 0`. The pooler-safety work is half done and the half that is done is the half that matters least (the checkpointer is 10 of 28 connections).

**Failure scenario.** An operator scales to 4 replicas. The fourth replica boots, `alembic upgrade head` succeeds (it needs 1 connection), the app starts serving, and then under any concurrency the SQLAlchemy pool cannot grow past its current checkouts: requests fail with `TooManyConnectionsError` from asyncpg or, worse, `pool_pre_ping` starts failing on healthy connections and the engine begins recycling into a refusal loop. The other three replicas start seeing failures too, because the fourth replica's overflow is stealing from the shared budget. The failure is fleet-wide and looks like a Postgres problem.

**Remediation** (small for the sizing, medium for the pooler). (a) Make `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle` and the checkpointer `max_size`/`min_size` config-driven and document the per-replica budget as `replicas × budget ≤ max_connections − reserve`. (b) Export `concierge_db_pool_checked_out` / `_overflow` gauges so the ceiling is visible before it is hit. (c) If a pooler is adopted: add the asyncpg `connect_args` above, route only the SQLAlchemy engine through it, and give the three session-scoped connections a direct DSN (a second `DATABASE_URL_DIRECT` env var).

---

### B3 — The chat SSE stream is not survivable behind a real load balancer: the heartbeat exceeds every common idle timeout, and reconnection duplicates the answer

Two defects that compound into one user-visible failure.

**Evidence — the heartbeat is too slow**

- `backend/app/api/chat.py:207-211` — the generator waits `asyncio.wait_for(queue.get(), timeout=120)` and emits a `ping` only after **120 seconds** of silence.
- Default idle timeouts of the proxies this will actually sit behind: AWS ALB **60 s**, GCP external HTTPS LB backend timeout **30 s**, Azure Application Gateway **20 s**, Cloudflare **100 s**. Every one of them is shorter than 120 s.
- `frontend/nginx.conf:14` sets `proxy_read_timeout 3600s`, which correctly handles the *last* hop — and is exactly why this will look fine in `docker compose up` and fail on first deploy.
- Contrast `backend/app/ambient/channels.py:139` — `STREAM_KEEPALIVE_S = 15.0`. The ambient stream is fine. Only chat is wrong.

A run that spends 90 s in a single long provider call emits nothing in that window (tokens stream only during generation; a `plan` step or a slow MCP tool is silent). The LB cuts the connection at 60 s.

**Evidence — there is no resumption**

- `backend/app/api/chat.py:202, 211, 213` — every yielded dict is `{"event": …, "data": …}`. **No `id` key.** sse-starlette emits an `id:` line only when the dict carries one, so the wire format has no event ids.
- Consequently the browser never populates `Last-Event-ID`, and `chat_stream` has no parameter or handler for it. `grep -rn "Last-Event-ID" backend/ frontend/src/` returns nothing.
- `frontend/src/api/client.ts:114-117` — `source.onerror` deliberately does nothing: *"EventSource retries automatically; close only when server ends"*.
- On reconnect, the handler replays the **entire** history (`chat.py:200-206`, `EVENT_BUS.subscribe` returns `list(entry["history"])`).
- `frontend/src/pages/ChatPage.tsx:400-401` — `setTokens((t) => t + String(event.payload.text ?? ''))`. An accumulator. The reset at `ChatPage.tsx:390-394` is keyed on `runId`, which has not changed.

**Failure scenario.** A user asks a question. The run takes 3 minutes. Behind an ALB the stream is cut at 60 s, EventSource silently reconnects, the server replays every `token` event emitted so far, and the accumulator appends them to what is already on screen. The user watches their answer duplicate itself — twice at 120 s, three times at 180 s. There is no error, no console message, and the persisted `runs.final_answer` is correct, so the bug vanishes on page refresh and is nearly unreproducible from a bug report.

At N replicas it gets worse: the reconnect can land on a replica that never ran the run, where `EVENT_BUS` is empty and the stream simply hangs emitting pings forever (`arch-C3b`).

**Remediation** (small). (a) Drop the chat heartbeat to 15 s to match the ambient stream, and make it a setting. (b) Attach a monotonic sequence number to every bus event and emit it as `id:`; accept `Last-Event-ID` in `chat_stream` and slice the replayed history from that offset. (c) Make the frontend accumulator idempotent by tracking the highest applied event id. (b) and (c) are also the precondition for ever moving the bus out of process memory.

---

## High

### H1 — There is no deploy lifecycle: no readiness gate, no drain, no graceful-shutdown budget, and SSE actively prevents a clean stop

`arch-M3` reports the missing `/ready` split and `arch-H2` reports that in-flight runs are lost at shutdown. Neither examines the deploy mechanics, which are worse than the sum:

- `backend/Dockerfile` CMD is `uvicorn app.main:app --host 0.0.0.0 --port 8000` — **no `--timeout-graceful-shutdown`**. Uvicorn's default is `None`, i.e. on SIGTERM it stops accepting new connections and then waits **indefinitely** for existing ones to close.
- Existing connections include every open SSE stream, and `chat_stream`'s generator only returns on a terminal event or client disconnect (`chat.py:214-215`). A stream on a `paused_hitl` run never terminates. **Uvicorn will never shut down cleanly while any chat page is open.**
- `docker-compose.yml` sets no `stop_grace_period` (default 10 s) and no `restart:` policy. So the sequence on every deploy is: SIGTERM → uvicorn waits on SSE → 10 s → SIGKILL → `arch-H2` (every in-flight run abandoned as `status='running'` forever, every post-run memory task dropped, every ambient fire's delivery never written).
- There is no `preStop` hook, no readiness endpoint to fail first, and `/health` returns 200 unconditionally (`main.py:135-137`) — so the LB keeps sending *new* traffic to a replica that is already terminating.
- **The leader lease has a correct release path that the shutdown sequence cannot reach.** `backend/app/ambient/drain.py:245` calls `await lease.release()` after the `while not stop.is_set()` loop exits, with the comment *"a clean stop releases the lease NOW"* — exactly right. But `backend/app/main.py:94-95` does `ambient_stop.set()` and then *immediately* `ambient_loop_task.cancel()`, without awaiting the task. The loop is parked in `asyncio.wait(...)` at `drain.py:240`, so `CancelledError` is raised there and the loop never re-checks `stop.is_set()`, never falls through, and never reaches line 245. The lock still clears when the connection dies with the process — but only at SIGKILL, so the ambient plane has no leader for up to one tick (default 60 s) per replica, sequentially. **A rolling deploy of 3 replicas is ~3 minutes of no ambient evaluation**, for want of an `await` before the `cancel()`.

**Remediation** (medium). Add `/ready` (DB `SELECT 1` under timeout, pool has headroom, migrations at head) and wire it to the LB. Add a `SHUTTING_DOWN` flag that `/ready` honours and that makes `chat_stream` emit a terminal `run_status: interrupted` and return. Set `--timeout-graceful-shutdown 30`, a `stop_grace_period: 45s`, and a `preStop` sleep long enough for the LB to deregister. Release the lease explicitly in the lifespan teardown. Then `arch-H2`'s run-drain becomes implementable.

---

### H2 — Memory recall can never be indexed: the vector column has no declared dimension

**Evidence**

- `backend/app/models/memory.py:110` — `embedding: Mapped[Any] = mapped_column(Vector(None))`. Same at `:147`.
- `backend/alembic/versions/a1b2c3d4e5f6_memory_layers.py:94, 104` — the table is created with `Vector(None)` and the only index is `memory_embeddings_model_idx` on `model_key`. `grep -rn "ivfflat\|hnsw" backend/alembic/` returns **nothing**.
- pgvector refuses to build an ivfflat or hnsw index on a column without a fixed dimension (`ERROR: column does not have dimensions`). This is not an oversight in a migration — it is a direct consequence of the deliberate provider-agnostic dimension strategy documented at `models/memory.py:99-102`.
- `backend/app/memory/rank.py:137-152` — the recall query is `ORDER BY e.embedding <=> CAST(:qvec AS vector) LIMIT :n`. With no index this is a full scan of every `memory_embeddings` row for the active `model_key`, computing a distance per row.

**Arithmetic.** A 1536-dim `vector` is 1536 × 4 + 8 = **6152 bytes**, well over the 2 kB TOAST threshold, so every row is stored out-of-line and each distance computation costs a TOAST fetch and a decompress.

| Memories | Vector heap scanned per recall | Realistic recall latency |
|---|---|---|
| 10 000 | ~62 MB | ~0.2–0.5 s |
| 100 000 | ~620 MB | ~2–6 s |
| 1 000 000 | ~6.2 GB | ~30–60 s |

`recall()` is on the memory-injection path of every run when `memory_enabled` is true. Adding replicas is actively harmful here: N replicas issue N× concurrent 6 GB scans against one Postgres, evicting each other's buffer cache.

**Remediation** (medium). Keep `Vector(None)` as the ingest/staging shape, but maintain a dimension-typed projection per active model — either one table per `model_key` created by the backfill job (`CREATE TABLE memory_embeddings_1536 (…, embedding vector(1536))` + `CREATE INDEX … USING hnsw (embedding vector_cosine_ops)`), or a single typed column plus a partial index, rebuilt by the existing `embedding_backfill` job on a model switch. The port surface (`get_embeddings`) is unchanged. Also add `CREATE INDEX CONCURRENTLY` discipline: an hnsw build on 1 M rows takes tens of minutes and locks writes without it.

---

### H3 — The HTTP rate limiter is per-process, so N replicas grant N× the configured budget, and its bucket dict never evicts

**Evidence**

- `backend/app/auth.py:46` — `_buckets: dict[str, tuple[float, float]] = {}` keyed by user or IP, module-level.
- `backend/app/auth.py:180-186` — the token bucket reads and writes only `_buckets`; nothing is shared.
- `backend/app/auth.py:210-211` — `burst` and `per_s` come from the live settings (`rate_limit_burst` 120, `rate_limit_per_s` 10).
- `grep -rn "_buckets.pop\|_buckets.clear" backend/app/` — no eviction anywhere.

**Failure scenario at N replicas.** The operator sets `rate_limit_per_s: 10` intending 10 rps per user. With round-robin routing across 3 replicas a single client sustains **30 rps** and bursts to **360**. Sticky routing accidentally repairs this — until a replica dies and the client's bucket resets to full on its new home, which is precisely the moment you least want a burst.

Separately, `_buckets` is an unbounded map keyed on user id *or client IP*. In the default posture (`AUTH_ENABLED=0`) the limiter never runs; with auth on, an internet-facing deployment accumulates one tuple per distinct source IP forever — a slow memory leak with an externally controlled key.

**Remediation** (small). Move the bucket to Postgres (`UPDATE … SET tokens = …, ts = now() WHERE key = … RETURNING tokens`, one round-trip) or to Redis when it is present, and evict idle keys. Note `arch-H14`'s point that the limiter should also apply with auth off — the same change covers both.

---

### H4 — Metrics cannot be scraped correctly from N replicas, and no autoscaling signal exists

**Evidence**

- `backend/app/main.py:139-143` — `/metrics` serves the default prometheus_client registry, which is **per process**.
- `frontend/nginx.conf:22-24` — `location /metrics { proxy_pass http://backend:8000; }`. Under `--scale backend=N` Docker's embedded DNS round-robins `backend`, so consecutive scrapes hit different replicas.
- No metric carries a replica or instance label (`backend/app/obs.py:48-81`). Prometheus would normally supply `instance` from the target — but the target here is one VIP, so every replica's series collapse into one.
- `backend/app/obs.py:75` — `AMBIENT_LEADER` is a `Gauge` with no labels.

**Failure scenario.** Prometheus scrapes `concierge_runs_total` and gets replica 1's counter (say 400), then replica 3's (say 120). `rate()` sees a counter reset and emits a spike, then a gap. Every dashboard built on these counters is wrong in a way that looks like real traffic variation. `concierge_ambient_leader` oscillates between 1 and 0 with no relationship to whether leadership is healthy.

**No autoscaling signal exists.** CPU is the wrong metric for an LLM-bound app — a replica saturated with 200 in-flight provider calls sits near 0 % CPU. The right signals are *saturation of the scarce resources*, and none of them are emitted:

| Signal | Emitted today? |
|---|---|
| In-flight runs (`len(RUNNING_TASKS)`) | No |
| DB pool checked-out / overflow / checkout-wait | No |
| Open SSE subscribers (chat + ambient) | No |
| Ambient event backlog (`ambient_events WHERE verdict IS NULL`) | No |
| Delivery backlog (`deliveries WHERE delivered_at IS NULL`) | No |
| Time-to-first-token / queue wait | No |
| LLM call latency and error rate per provider | No (`arch-M7`) |

**Remediation** (small–medium). Add a `replica` label sourced from `HOSTNAME` to every metric family (or, better, scrape replicas individually via a headless service / per-container port and let Prometheus own `instance`). Add the seven saturation signals above. The correct HPA metric for this workload is **in-flight runs per replica** with a target well under the pool ceiling, with **ambient event backlog** as a secondary. Neither can be used today because neither exists.

---

### H5 — The registry cache has two coherency races that only manifest at N>1, and Redis blobs have no TTL to bound them

Neither review covers the cache's internals under concurrency. `arch-H4` covers redis-read failure; `arch-M1` covers the listener never reconnecting. These are different.

**Race A — a peer invalidation arriving during a reload is silently discarded (memory mode).**

`backend/app/registry_cache.py:376-382`:

```python
if force or registry in self._dirty or registry not in self._data:
    data = await _load_registry(registry)   # ← await: the listener callback runs here
    self._data[registry] = data
    self._loaded_at[registry] = ...
    self._dirty.discard(registry)           # ← discards the invalidation raised during the load
```

`_mark_dirty` (`:214-245`) does **not** take `self._locks[registry]`, so a NOTIFY arriving while `_load_registry` is awaiting sets `_dirty`, and the loader then unconditionally discards it. The replica serves the pre-write snapshot **until the next unrelated write to that registry** — potentially forever on a quiet registry. Note that `self._generation[reg]` is incremented on every dirty-mark (`:232`) and is the exact mechanism that would close this race, but `_ensure` never reads it.

**Race B — a slow read-through resurrects a deleted blob, permanently (redis mode).**

`backend/app/registry_cache.py:362-375`: on a miss, replica A calls `_load_registry` (an await), then `redis.set(key, json.dumps(data))`. Meanwhile a write on replica B calls `redis.delete(key)` (`:237`). If B's delete lands between A's read and A's set, **A writes the stale snapshot back**. And `redis.set` is called with no `ex=` — `grep -n "expire\|setex\|ex=" backend/app/registry_cache.py` returns nothing. There is no TTL anywhere. The stale blob is now authoritative for **every** replica until the next write to that registry.

**Failure scenario.** An operator deactivates a destructive tool. The write commits, the NOTIFY fires, and one replica loses the dirty flag (A) or the Redis blob is resurrected (B). The tool keeps executing in runs on the affected replicas, and `GET /cache/status` reports a healthy, higher `generation` — because the generation counter *was* bumped; only the data wasn't reloaded. The status endpoint actively lies.

**Remediation** (small). (a) Snapshot the generation before the load and only discard the dirty flag if it is unchanged: `gen = self._generation[reg]; data = await _load(); if self._generation[reg] == gen: self._dirty.discard(reg)`. (b) In redis mode, use the same guard before the `set`, and add a defensive TTL (`ex=300`) so no coherency bug can outlive five minutes. (c) Make `/cache/status` report `dirty` alongside `generation` so the divergence is visible.

---

### H6 — Every replica connects to every MCP server: N× subprocesses, N× health pings, and a tool-ingest race with a persistent failure state

**Evidence**

- `backend/app/mcp/manager.py:79-91` — `start()` connects **every** non-deleted server on every replica.
- `backend/app/mcp/manager.py:132-137` — stdio servers are spawned as subprocesses (`uvx mcp-server-fetch`, `npx @modelcontextprotocol/server-filesystem`). The seed ships two.
- `backend/app/mcp/manager.py:261-268` — a health loop pings every server every `mcp_health_interval_s` (default 30 s), per replica.
- `backend/app/mcp/manager.py:191` — `_ingest` reads `taken_keys = set(SELECT tool_key FROM tools)` — a full-table read — and then inserts new rows.
- `backend/alembic/versions/ebf05a862e33_initial_schema.py:218` — `ix_tools_tool_key` is **unique**.
- `backend/app/mcp/manager.py:121` — `_ingest` failure inside `connect_server` is caught by the `except BaseException` at `:122`, which tears down the connection and records `status='error'`.
- `arch-H10`: nothing ever reconnects an `error` server.

**Failure scenarios.**

(a) *Resource multiplication.* At N=3 with 2 seeded stdio servers, that is 6 node/python subprocesses in 3 containers, each ~50–150 MB RSS, with no `pids-limit` and no memory limit in compose (`code-M15`). Against a *remote* HTTP MCP server, N replicas × 2 pings/min is N× the load and N× the connection count on a third party's service.

(b) *Ingest race with permanent consequence.* On a cold boot into an empty `tools` table, all N replicas compute the identical `key = f"{server.name}.{spec.name}"`, all N insert, one commits and N−1 get a unique-violation. The whole `_ingest` transaction fails → `connect_server` records `status='error'` and tears down → **those replicas have zero MCP tools**, and per `arch-H10` nothing retries. Skills bound to those tools silently degrade on 2 of 3 replicas, and which behaviour a user gets depends on which replica the load balancer picked. Same shape on a simultaneous `listChanged` that adds a tool (though `_safe_refresh` swallows it without the status change, so the failure is quieter and equally persistent).

**Remediation** (small–medium). Use `INSERT … ON CONFLICT (tool_key) DO NOTHING` and re-read, so a losing racer is a no-op rather than a transaction abort. Gate the whole ingest behind a per-server advisory lock so only one replica reconciles. Make health-ping ownership leader-only (the connection can stay per-replica; the *status writes* should not be N-way contended). Add a `concierge_mcp_server_connected{server}` gauge so a partially-degraded fleet is visible.

---

### H7 — There is no cost model and no spend ceiling anywhere; a runaway loop's only bound is a hardcoded constant on ambient runs

**Evidence**

- `grep -rniE "\b(cost_usd|price|pricing|usd|spend)\b" backend/app/ --include='*.py'` returns **two comment hits and nothing else**. There is no price table, no per-model rate, no cost metric, no cost column.
- Token accounting exists (`runs.total_input_tokens/total_output_tokens`, `models/run.py:73-74`) but is never converted to money, and is itself lossy under parallel dispatch (`code-M2`).
- `backend/app/ambient/execute.py:33-38` — `DEFAULT_BUDGETS` (`max_steps: 40`, `max_tokens: 200_000`, `wall_clock_s: 900`) are **module constants, not settings** — they cannot be tuned without a redeploy, and they violate the project's own §3.7 "every autonomous behavior has a live switch" discipline.
- These budgets are enforced only by `_supervise` (`execute.py:169-209`), reached only from `execute_fired_event`. **Chat runs, direct runs and eval runs have no token budget, no step budget and no wall clock** (`arch-H1`).
- There is no per-user, per-tenant, per-day or per-deployment aggregate ceiling of any kind. `ambient_runs_per_day` (default 50) caps ambient *run count*, not spend, and applies to nothing else.
- `backend/app/api/evals.py:151` — `asyncio.create_task(execute_eval_run(...))` per dataset, uncapped, iterating every case in the CSV.

**Failure scenario with an invoice.** An agentic run enters a tool-call loop (`agentic_recursion_limit` is 100 model calls; `max_tool_iterations` defaults to 8 per skill, and a multi-worker plan multiplies both). At Sonnet-class pricing with a 50 k-token context, 100 model calls is roughly $15–30 for **one run**. `arch-H14` establishes that `POST /chat` has no admission control at all; 200 such requests is $3–6 k in a few minutes, spread across N replicas so no single process looks anomalous, with no metric that would page anyone. The first signal is the provider invoice.

At N replicas this is strictly worse: per-replica limits (if any were added) would each need to be `budget/N`, and there is no shared accounting substrate to do it properly.

**Remediation** (medium). (a) Promote `DEFAULT_BUDGETS` to settings and apply them to **all** runs, not just ambient — the supervisor logic already exists. (b) Add a static price table keyed on `provider:model` (input/output per 1 M tokens) in `app/llm/`, derive `runs.cost_usd` at finish, and emit `concierge_run_cost_usd` as a histogram labelled by model. (c) Add a shared spend ceiling as a Postgres counter: `SELECT sum(cost_usd) FROM runs WHERE started_at >= date_trunc('day', now()) [AND user_id = …]`, checked at run admission, returning 429 with a clear reason. That is one indexed aggregate per run start — affordable, and correct across replicas by construction.

---

### H8 — The embedding backfill runs on every replica at every boot, with no lock

**Evidence** — `backend/app/main.py:67` — `backfill_task = asyncio.create_task(backfill_embeddings())` in the lifespan of every process. `backend/app/retrieval.py:310+` — `backfill_embeddings` embeds every record whose `embedding_hash` is stale. There is no `acquire_job_lock` on this path (contrast the periodic jobs at `memory/lifecycle.py:344-355`, which do lock).

**Failure scenario.** A rolling deploy after an `embedding_model` change brings up 3 replicas. All three walk the same stale-hash set and call the embeddings API for every tool, skill and sub agent — 3× the calls, 3× the spend, and 3 racing `UPDATE`s per row, each followed by a `cache.invalidate(kind)` and its `pg_notify` (`retrieval.py:301`). With ~200 registry records that is ~600 embedding calls and ~600 cross-replica NOTIFY broadcasts in the first minute of every deploy — a self-inflicted invalidation storm that also guarantees H5's races fire.

**Remediation** (small). Wrap `backfill_embeddings` in the existing `acquire_job_lock` helper with its own job id, exactly as the consolidation jobs do. Batch the invalidation to one call at the end rather than one per record.

---

## Medium

### M1 — Browser connection limits: nginx serves HTTP/1.1, and each tab holds two persistent SSE streams

`frontend/nginx.conf:2` is `listen 80;` with no `http2`. Browsers cap HTTP/1.1 at 6 concurrent connections per origin. Each open tab holds `/chat/stream/{id}` (`client.ts:78`) plus `/ambient/stream` (`AmbientToaster.tsx:34`) = 2 persistent. TanStack Query polls `/runs` every 3 s, `/conversations` every 5 s, ambient ledger every 2 s, and more (`frontend/src/api/hooks.ts:22,30,38,60,69,100,109,125`). **At three open tabs all 6 slots are persistent SSE and every poll queues indefinitely** — the UI freezes with no error. This is not exotic: an operator with Chat, Runs and Settings open in three tabs hits it. `http2 on;` plus TLS is a one-line fix and raises the limit to ~100 streams on one connection.

### M2 — Per-process ambient pattern cooldown means N× pattern fires

`backend/app/ambient/patterns.py:31` — `_recent_fires: dict[tuple[str, str], datetime]`, consulted by `_cooled_down` (`:44-48`) with a 300 s default cooldown. `advance_patterns` runs inside `default_processor`, which every replica executes via the SKIP-LOCKED drain (`drain.py:51-58, 216-218`). Each replica has its own cooldown map, so a pattern rule can fire up to N× per cooldown window — one derived event, one run, and one delivery per replica that happened to claim a matching source event. Move the watermark to a column on `pattern_instances` / `standing_intents` with a guarded `UPDATE … WHERE last_fired_at < now() - interval`.

### M3 — Per-replica OAuth token cache multiplies token-endpoint traffic

`backend/app/a2a/auth.py:47` — `_TOKEN_CACHE: dict[(agent_id, scheme), (token, expires_at_monotonic)]`, keyed on **process-monotonic** time. N replicas each fetch and hold their own client-credentials token for every remote agent. Some IdPs rate-limit the token endpoint or issue single-use tokens; more commonly this just multiplies the audit-log volume by N and makes token revocation take up to N× longer to take effect. Low blast radius today (a2a is dark by default) but it is a shared-cache-shaped hole. Move to a `a2a_tokens` table with `expires_at` as a timestamptz, or to Redis when present.

### M4 — Leader-only watermarks reset on every failover

`backend/app/a2a/poller.py:35` — `_last_poll_monotonic` gates the parked-task poll to `a2a_poll_interval_s`. It is per-process and monotonic-based, and `poll_parked_tasks` runs only on the leader. On every leadership change (a deploy, a crash, a DB blip that drops the lease connection) the new leader's watermark is `None`, so it polls immediately regardless of interval — and at `a2a_max_parked` (20) × 15 s that is up to 300 s of leader-tick blockage right after a failover, when the tick can least afford it. Same shape for `memory/lifecycle.py:82`'s `_LAST_RUN` (covered as `arch-C3`). Persist both watermarks as rows.

### M5 — Presence evaluation opens one session per user per tick, on the leader

`backend/app/ambient/presence.py:66-88` — `evaluate_presence` selects **all** `UserPresence` rows and then opens a fresh session inside the loop for each one. At 1 000 users that is 1 001 session checkouts on the leader replica every tick (default 60 s), against a 15-connection pool. The clients meanwhile write a heartbeat every 30 s (`record_heartbeat`, one session each) — 2 000 writes/minute spread across N replicas. The read side should be a single `UPDATE … FROM (…) WHERE state IS DISTINCT FROM …  RETURNING` and the transitions derived from the returned rows.

### M6 — Data growth: no partitioning, no retention, an unbounded purge, and an undefined RTO

`arch-M6` enumerates the six tables with no retention job; this is the volumetric consequence.

- **`run_steps` is the growth driver.** One row per step with JSONB `input`/`output`. At ~15 steps/run and ~2 kB/step: 1 000 runs/day → 15 k rows/day → **5.5 M rows and ~30 GB/year** with TOAST. No partitioning (`grep -n "PARTITION" backend/alembic/versions/*.py` → nothing), no retention.
- **The purge is one unbounded `DELETE`.** `backend/app/api/runs.py:99-106` deletes every `run_steps` row, every `runs` row and all three checkpoint tables in one transaction. At 5 M rows that is a multi-GB WAL burst, a long-held lock, and an autovacuum backlog that will not clear for hours. There is no batched/chunked path.
- **Autovacuum on high-churn tables.** `ambient_events` and `deliveries` are `UPDATE`-heavy (verdict writes, `delivered_at`, `seen_at`, `external` jsonb merges) with default `autovacuum_vacuum_scale_factor = 0.2` — meaning vacuum waits until 20 % of the table is dead before running, which on a large table means a large, disruptive vacuum. Neither table has per-table autovacuum settings.
- **Backup RTO/RPO are undefined.** `docs/operations/data-lifecycle.md` documents `pg_dump -Fc` + `pg_restore` and is honest about what a dump does *not* restore, but states no target and no measurement. A 30 GB `-Fc` restore with index rebuilds (including any future hnsw index, see H2) is measured in **hours**, and there is no WAL archiving or PITR — so RPO is "since your last manual `pg_dump`". For a system whose entire state is one database, that is the single largest unquantified operational risk.
- **Index bloat.** The `memories_fts_idx` GIN index (`models/memory.py:40`) is on a `Computed` tsvector over a high-churn table; GIN indexes bloat under update load and need periodic `REINDEX CONCURRENTLY`. Nothing schedules it.

**Remediation** (medium). Declaratively partition `run_steps` and `runs` by month (`PARTITION BY RANGE (started_at)`) so retention is `DROP PARTITION` rather than `DELETE`. Batch the purge. Set per-table autovacuum thresholds on `ambient_events`, `deliveries`, `memories`. Adopt WAL archiving (pgBackRest / cloud-native snapshots), state an RTO/RPO target, and **restore-test it once** so the number is measured rather than assumed.

### M7 — The compiled-worker cache is per-replica, cold after every deploy, and never evicts

`backend/app/factory/worker.py:625` — `_WORKER_CACHE: dict[(sub_agent_id, updated_at, id(checkpointer)), CompiledStateGraph]`. Two consequences at N>1: (a) each replica pays its own compile cost, so a rolling deploy costs N cold-start penalties rather than one, and the p99 latency spike after a deploy is N× longer than a single-node test would predict; (b) `updated_at` is part of the key and old entries are never dropped, so every registry edit permanently adds an entry — an unbounded, edit-driven memory leak on top of `arch-H3`. Add an LRU bound and evict by `sub_agent_id` on `invalidate("sub_agents")`.

### M8 — There is no CI, so none of this can be regression-gated

`ls -a` shows no `.github`, no `.gitlab-ci.yml`, no CI configuration of any kind. `CLAUDE.md` defines the gates (`pytest`, `ruff`, `mypy`, `python -m app.doclint`, `npm run lint && npm run test`) and the Dockerfile enforces `doclint` at build time — but nothing runs the test suites automatically. Every fix in this document, and both prior documents, is therefore unprotected against regression. This is the cheapest item on the list and the one that determines whether the others stay fixed.

### M9 — Per-replica cold caches multiply provider calls

`backend/app/retrieval.py:29-30` — `_QUERY_VECS` (128-entry FIFO of query embeddings) is per-process, so the same user query issued to a different replica pays a fresh embeddings call. `backend/app/llm/registry.py:48` constructs a fresh chat model — and a fresh httpx client — on every call (`arch-M10`/`code-M1`), which at N replicas means N× the TLS handshake and connection churn against each provider, and N× the file-descriptor pressure. Neither is severe alone; together they mean "add a replica" costs more than it looks like on the provider side.

---

## Low

- **`_next_sub` monotonic counter** (`channels.py:137`) is per-process, so subscriber ids collide across replicas. Harmless today (ids are never persisted or compared cross-process) but it forecloses using them as a shared key when B1 is fixed.
- **`include_memories` conversation creation races.** `backend/app/ambient/execute.py:95-118` — two replicas draining two fires for the same routine both find `owner.conversation_id is None` and both create a conversation; one wins the write and the other is orphaned, silently splitting a routine's continuity history. A guarded `UPDATE … WHERE conversation_id IS NULL RETURNING` fixes it.
- **`_runs_today_cap_reached` is read-then-decide** (`decide.py:60-72`) across concurrent replica drains, so `ambient_runs_per_day` can be overshot by up to N. Same shape as `arch-H13`; lower stakes.
- **`docs/operations/scaling.md` is the best artefact in this area and is now partly wrong.** Its §"SSE and run execution: sticky is mandatory" is correct as far as it goes but presents affinity as sufficient. Its retrieval section describes the pgvector swap as future work for *registry* embeddings while `memory_embeddings` is already pgvector and un-indexable (H2). Both should be corrected when the findings above are actioned.

---

## The sticky-session analysis

`docs/operations/scaling.md:34` states the requirement as: *"session-affinity routing keyed so that a conversation's chat POST, its stream GET, and its control POSTs hit the same replica."* Here is what that actually buys.

### What sticky routing fixes

| Broken path | Why affinity repairs it |
|---|---|
| `GET /chat/stream/{run_id}` after `POST /chat` | The run task and its `RunEventBus` entry live in the process that served the POST (`runner.py:88-91`, `context.py:49`). Same replica ⇒ real history and live events. |
| `POST /runs/{id}/cancel` | `cancel_run` looks the task up in the process-local `RUNNING_TASKS` (`runner.py:580-594`). Same replica ⇒ the cancel actually cancels instead of writing a false `cancelled` (`arch-C3a`). |
| `POST /runs/{id}/hitl` resume | Any replica *can* resume from the shared Postgres checkpoint, but the resumed run's events stream from the resuming replica. Affinity keeps the resume and the open stream co-located. |
| `POST /evals/datasets/{id}/run` + its progress polls | `_RUN_TASKS` is process-local (`api/evals.py:28`), though the progress itself is DB-backed (`EvalRun` row), so this one is only half a problem. |
| Rate-limiter fairness | Accidentally: one bucket per user on one replica approximates the intended limit (H3). |

That is a real and non-trivial list. Affinity is necessary.

### What sticky routing does **not** fix

These are the paths where **no client and therefore no routing key exists**:

1. **Ambient run execution.** `execute_fired_event` (`ambient/execute.py`) starts a run on whichever replica's SKIP-LOCKED drain claimed the event. There was no HTTP request, so there is no cookie, no session, no key. The run creates a `[ambient] …` conversation (`execute.py:106-112`) that a user then opens in the Chat page — and `streamRun` connects them to *their* sticky replica, which is not the executing one. **A user can never watch an ambient run stream.** This is the flagship autonomous feature and affinity is structurally incapable of fixing it.
2. **The delivery/toast plane (B1).** The leader publishes; the user is stuck to a different replica. The leader is elected, not routed to.
3. **`POST /routines/{id}/fire`.** Explicitly exempt from auth (`auth.py:49`) because it is called by external webhook senders. Those senders carry no affinity cookie and will not.
4. **Rolling deploys.** Affinity is *defined* as broken by a deploy. Every stickiness scheme's guarantee ends the moment its target replica terminates, which is exactly when in-flight runs are abandoned (H1 + `arch-H2`) and reconnects land on an empty `EVENT_BUS`.
5. **Replica death.** Same, unscheduled. The client's next request routes to a fresh replica, `EVENT_BUS` is empty, the stream hangs on 120 s pings (B3), and the run row says `running` forever.
6. **Consolidation and the ambient tick.** Neither is client-initiated. Leader-only work is leader-only regardless of routing.
7. **The `_recent_fires` cooldown (M2), `_TOKEN_CACHE` (M3), `_LAST_RUN`, `_WORKER_CACHE` (M7), `_QUERY_VECS`.** Per-process state that is not keyed on a client at all.

### What sticky routing introduces

1. **There is no key to be sticky on.** With `AUTH_ENABLED=0` (the default) the backend sets no session cookie and there is no user identity. The LB must fall back to source-IP hashing, which collapses to a handful of buckets behind corporate NAT or a mobile carrier CGNAT — producing *worse* balance than round-robin while still not guaranteeing affinity for a user whose IP changes mid-run. If affinity is adopted, the backend must issue an LB-readable affinity cookie.
2. **Load imbalance, because the unit of stickiness is not the unit of load.** A "session" here can be one idle tab, or an agentic run with `max_parallel_dispatch: 4` workers each running 8 tool iterations against 200 k tokens for four minutes. Hashing distributes *sessions*, not *work*. With no admission control (`arch-H14`) and no in-flight-run gauge (H4), a single heavy user pins one replica into pool exhaustion while the others idle — and neither the LB nor any dashboard can see it.
3. **Drain becomes the hard problem.** A sticky replica cannot be drained by simply removing it from rotation: its sessions are pinned to it and its runs can last minutes or (at a HITL gate) up to `ambient_hitl_timeout_h` = 24 hours. Draining honestly means either a very long grace period or a run-handover mechanism, and neither exists (H1). In practice deploys will just kill the sessions.
4. **Autoscaling stops working in both directions.** *Scale-out*: new replicas receive no traffic, because existing sticky sessions stay pinned to the hot replicas that triggered the scale-out. Utilisation stays high, the HPA scales out again, and you accumulate idle replicas — each consuming 28 Postgres connections against a 3-replica budget (B2). *Scale-in*: terminating any replica kills the sticky sessions and in-flight runs on it. The two effects together make an autoscaler actively harmful here, which is worth stating explicitly because it is the opposite of the usual intuition.
5. **It hides the bug rather than fixing it, and hides it *non-deterministically*.** With affinity, `POST /runs/{id}/cancel` usually works — so the false-`cancelled`-while-still-running path (`arch-C3a`) becomes an intermittent production mystery instead of a reproducible bug.

### Verdict

Affinity is a **necessary mitigation for the chat plane and nothing else**. It is not a scaling strategy: it converts a deterministic failure into an intermittent one, blocks autoscaling, and leaves the ambient plane — the system's most distinctive capability — broken at N>1 in three separate ways (B1, and items 1 and 3 above). Adopt it only alongside an explicit statement that ambient mode is single-replica-effective until B1 and the event bus are fixed.

---

## Proposed load-test and capacity-model plan

None of this exists today (`grep -rli "locust\|k6\|load test"` finds only prose in docs). The point of the plan below is to make the bottleneck order *falsifiable* rather than argued.

### Environment

Two shapes, both required, because several findings only appear in one:

- **Single-replica** — establishes per-replica capacity, which is the denominator of every capacity claim.
- **3-replica behind a real proxy** (nginx or envoy configured with a **60 s idle timeout**, not the repo's 3600 s) — this is the configuration that surfaces B3, and running it against the repo's own nginx will hide the finding.

Use `FAKE_LLM_ENABLED=1` **with an injected latency distribution** for the deterministic runs (provider latency is the dominant term and must be modelled, not eliminated), plus a smaller real-provider run to validate the fake's fidelity.

### Workload mix to simulate

| Scenario | Shape | Targets |
|---|---|---|
| **A. Chat concurrency ramp** | 1 → 200 concurrent `POST /chat` + held SSE, each run 4 steps / 30 s simulated provider latency | Find the knee. Expect the pool ceiling first. |
| **B. Idle SSE fan-out** | 500 open `/chat/stream` on `paused_hitl` runs, no traffic | Isolates `arch-C1` (a stream pins a connection) and B3's heartbeat. This is the cheapest test with the highest information yield. |
| **C. Long-run proxy survival** | 20 runs of 5 minutes each with a 90 s silent gap mid-run, behind a 60 s-idle proxy | Falsifies or confirms B3 end-to-end: measure duplicated tokens in the rendered answer, not just reconnect counts. |
| **D. Ambient burst** | 5 000 `ambient_events` injected in 60 s, ambient on, 3 replicas | Measures drain throughput (should scale with N) vs evaluator throughput (should not). Confirms the ceiling table's first two rows. |
| **E. Memory recall scaling** | Recall at 10 k / 100 k / 1 M memories | Confirms H2's curve. Expect superlinear latency growth with no index. |
| **F. Delivery reach** | 30 SSE clients across 3 replicas, 100 tier-0 deliveries | Directly measures B1: expected reach is ~1/3. If it is not, B1 is wrong. |
| **G. Rolling deploy under load** | Scenario A at 50 % of the knee, then a rolling restart | Measures runs lost, streams broken, ambient dead-time, and 5xx during rollout (H1). |
| **H. Registry write storm** | 100 registry PATCHes across 3 replicas in `memory` cache mode, reading concurrently | Detects H5's lost-dirty window. Assert every replica converges within one read. |

### SLIs that matter for this workload

Latency percentiles on *request* duration are close to meaningless when a unit of work legitimately takes four minutes. The right set:

| SLI | Definition | Why |
|---|---|---|
| **Time to first token** | `POST /chat` → first `token` SSE event | The only latency the user actually feels. |
| **Run completion rate** | terminal `completed` / runs started | Catches abandoned-`running` runs (H1, `arch-H2`) that no request-level metric sees. |
| **Run duration p50/p95** | by `orchestrator_mode` | The capacity denominator: throughput = concurrency ÷ duration. |
| **Stream continuity** | fraction of runs whose client received `done` on the original connection | The single number that captures B3. |
| **Admission latency** | `POST /chat` response time | Should stay flat; if it degrades, event-loop starvation (`code-M9`, `code-M12`) is present. |
| **Delivery reach** | subscribers that received a toast ÷ subscribers connected | B1's SLI. Should be 1.0. |
| **Ambient tick completion rate** | ticks whose body completed ÷ ticks started | `arch-H6`'s SLI; currently unmeasurable. |
| **Pool saturation** | checked-out ÷ (pool + overflow), and checkout wait p99 | The leading indicator for every other failure. |
| **Cost per run** | p50/p95 USD | H7. |

### Expected bottleneck order — and how to falsify it

Stated as a prediction so the test can prove it wrong:

1. **DB connection pool exhaustion**, at roughly **12–15 concurrent SSE viewers** on one replica (`arch-C1` + a 15-connection budget). *Falsified if* scenario B reaches 100 idle streams with checkout-wait p99 under 10 ms.
2. **`run_steps` / `conversations` query cost** (`arch-C2`, `code-H1`), degrading `GET /runs` (polled every 3 s) once `run_steps` exceeds ~10⁵ rows. *Falsified if* `GET /runs` p95 stays flat as the table grows past 500 k rows.
3. **Provider concurrency and rate limits**, once 1 and 2 are fixed — the theoretically correct bottleneck for an I/O-bound LLM app. *Falsified if* the knee moves with replica count rather than with provider concurrency.
4. **Event-loop starvation** from the CPU-bound work on the loop: `xml.etree` parsing (`code-H9`), LLM-authored regexes (`code-M12`), and `shutil.disk_usage` (`code-L1`). *Falsified if* admission latency stays flat while run throughput saturates.
5. **Postgres CPU on memory recall** (H2), once memory is on and the corpus is non-trivial. *Falsified if* scenario E's latency is linear rather than superlinear in corpus size.
6. **Process memory** — `RunEventBus` history (`arch-H3`), `_buckets` (H3), `_WORKER_CACHE` (M7) — the slowest and most certain of the six.

If the measured order differs from this, the model is wrong and the capacity plan should be rebuilt from the measurement, not from this list.

### Capacity model to publish afterwards

One page, derived from the above:

```
runs_per_replica  = pool_headroom / connections_held_per_run
throughput        = concurrent_runs / mean_run_duration
replicas_needed   = peak_runs_per_second × mean_run_duration / runs_per_replica
max_replicas      = (max_connections − reserve) / 28      # today: 3
cost_per_hour     = runs_per_hour × mean_cost_per_run     # requires H7
```

Every one of those five inputs is currently unmeasured. That, not any individual bug, is the actual state of production readiness.

---

## Top 5, in fix order

1. **B3 — fix the SSE wire format: 15 s heartbeat, `id:` on every event, `Last-Event-ID` replay, idempotent client accumulator.**
   First because it is the only finding here that breaks the product *visibly, for every user, at N=1*, the moment a real load balancer is put in front of it — and it will be diagnosed as "the model repeated itself", i.e. as a model problem, costing weeks. It is also small, self-contained, and the mandatory precondition for ever moving the event bus out of process memory (which is the eventual fix for `arch-C3`). Cost: about a day.

2. **H1 — build the deploy lifecycle: `/ready`, a shutdown flag that terminates SSE streams, `--timeout-graceful-shutdown`, `stop_grace_period`, explicit lease release.**
   Second because until a deploy is safe, shipping the other fixes is itself the largest source of production incidents — every rollout currently abandons in-flight runs and blacks out the ambient plane for a minute per replica. It also converts `arch-H2` from "unfixable without a drain point" into a small change, and it is the prerequisite for any load test of scenario G.

3. **B2 — size the pools from config, export saturation gauges, and document the `replicas × 28 ≤ max_connections` budget.**
   Third because it is the ceiling that silently caps the fleet at three, and because the gauges are what make findings 1, 2 and 4 of the bottleneck prediction *observable instead of argued*. The gauge work is a couple of hours; the pooler question can be deferred until the budget is at least written down. Do not adopt pgbouncer without the asyncpg `connect_args` change — a pooler added today will fail with `DuplicatePreparedStatementError` and be blamed on Postgres.

4. **B1 — move the delivery broadcast and the presence oracle off per-process state.**
   Fourth because it is the one finding where N>1 produces *silently wrong autonomous behaviour* rather than degraded service: users miss interrupts they should have seen, get emails they should not have, and the salience learner is trained on the resulting false negatives. It is also the finding the spec actively defends, so it needs a decision recorded before it needs code. Both halves are `pg_notify` plus a small heartbeat table — no broker, §2 intact.

5. **H7 — a price table, `runs.cost_usd`, a cost histogram, and a shared daily spend ceiling checked at run admission.**
   Fifth rather than first only because the four above are prerequisites for measuring anything. But it is the finding with an unbounded downside: `arch-H14` establishes there is no admission control, H7 establishes there is no budget and no visibility, and the two together mean the first signal of a runaway loop is an invoice. The ceiling as a Postgres aggregate is correct across replicas by construction and costs one indexed query per run start.

**Immediately behind**: H2 (the un-indexable vector column — start it early, because the migration is slow and gets slower every week), H4 (metrics with a replica label — nothing above can be *confirmed* in production without it), and M8 (CI — the cheapest item here and the one that decides whether any of this stays fixed).
