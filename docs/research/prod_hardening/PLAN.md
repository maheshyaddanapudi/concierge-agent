# Production Hardening Program — M49 → M56

One program, eight stages, each with an exit criterion stated before work starts. Consolidates every
finding from the three reviews in this directory plus the seven gaps none of them covered. This is the
**MAX** scope: it absorbs everything a pilot needs (MIN) and everything a team needs (MED), and adds
horizontal scale, forkability, and release mechanics.

**Goal state:** a horizontally-scalable OSS core that a company can fork, implement one port against, and
run as an enterprise system — the Conductor model.

## Status

| Stage | State | Evidence |
|---|---|---|
| M49 | ✅ done | `docs/acceptance/prod/M49/` — baseline (before any fix), prompt-harness proof, ruff triage |
| M50 | ☐ | |
| M51 | ☐ | |
| M52 | ☐ | |
| M53 | ☐ | |
| M54 | ☐ | |
| M55 | ☐ | |
| M56 | ☐ | |

## Scope decisions, recorded

| Decision | Consequence in this plan |
|---|---|
| **No auth implementation** | The `AuthProvider` *seam* is built (M55); nothing plugs into it. Default = today's no-op, byte-identical. |
| **No CI** | Every gate runs by hand. The plan's per-stage verification is the substitute — each stage ends with the full suite, lint, mypy, doclint, frontend gates, and executed proof, recorded. |
| **Fresh installs only** | No upgrade-path or data-migration work for running instances. M54's vector partitioning is a schema, not a migration of live data. |
| **No vulnerability scanning** | Out. Dependency pinning stays as-is. |
| **Sticky routing parked** | The shared control plane (M54) is the answer; sticky was only ever a partial mitigation and it makes autoscaling worse. |
| **§2 holds** | No broker, no queue, no Celery. Every distributed mechanism below uses Postgres, which the system already requires. |

## Verification discipline

Per CLAUDE.md: a stage is done when its tests are green **and** its executed proof is captured — test
output, load numbers, curl transcripts, and screenshots where the change is user-visible. Evidence lands
in `docs/acceptance/prod/<stage>/`. With no CI, each stage's closing gate is run and recorded by hand,
and the record is the commit.

Live proofs use `openrouter:qwen/qwen3.8-max` for every model role and `openai:text-embedding-3-small`
for embeddings, per the CLAUDE.md rule.

---

## M49 — Foundation: make measurement possible, make behavior testable

**Changes**
- Enable ruff `BLE` and `S`; triage every violation. The 69 `noqa: BLE001` and 2 `noqa: S608` markers
  suppress rules that were never enabled — the real violation count is unknown until they run, and that
  number is itself a finding. Keep a suppression only where the broad catch is genuinely correct (a loop
  that must survive anything); narrow the rest.
- Load-test harness (`experiments/load/`) driving the shipped API: concurrent chat runs, concurrent SSE
  subscribers, ambient tick under backlog, memory recall at seeded corpus sizes (1k / 10k / 100k).
- Capture and commit the **baseline before any fix**, so every later stage has a number to beat.
- **Prompt regression harness** *(uncovered gap)*: prompts in `backend/app/prompts/` define behavior and
  nothing gates a change to one. Wire the existing §15 evals machinery to a per-prompt golden set on the
  fake provider, so editing a prompt file runs its cases. The evals feature already exists; this connects
  it to the thing most likely to drift.

**Exit criteria**
- Baseline committed: p50/p95 latency, max concurrent SSE before failure, recall latency by corpus size,
  connections at rest and under load.
- `BLE`/`S` triage recorded — each surviving suppression justified in one line.
- Every prompt file has at least one golden case; a deliberate prompt regression fails the harness.

---

## M50 — The ceiling: the four ways this falls over first

Every item is a small diff. Together they remove the limits that make later measurement meaningful. This
stage is MIN on its own — nothing should be given to anyone before it lands.

**Changes**
- **Connection pool** (`arch-C1`): explicit `pool_size`/`max_overflow` from a stated replica budget;
  streaming endpoints take a session, read, release — never hold a request-scoped session for the life of
  a stream.
- **Indexes and loading** (`arch-C2` / `code-H1`): indexes on `runs.conversation_id`, `runs.status`,
  `runs.started_at`, `run_steps.run_id`, `tools.mcp_server_id`; explicit loading in place of
  `lazy="selectin"` at the call sites that need children; paginate `/runs` and `/conversations`; aggregate
  instead of `len(c.runs)`; frontend backoff instead of a fixed 3 s poll.
- **Memory filter unification** (`code-H5`): pinned selection routes through the same predicate builder
  as `recall()` — one definition of visibility. Fixes the live project leak and the dormant tenancy leak,
  and is the first step of M55.
- **Trigger validation** (`code-H4`): Pydantic models at the API boundary; per-evaluator try/except,
  timeout and error metric in the ambient tick; a repeatedly-raising routine is quarantined, not allowed
  to wedge the loop.
- **Timezone** (`arch-M4`): a timezone setting; quiet hours and digest times resolve in it. "Never
  interrupt you at night" is a promise the product makes explicitly and currently breaks for everyone not
  on UTC.

**Exit criteria**
- ≥ 50 concurrent SSE subscribers with no pool exhaustion; `/runs` p95 flat as run count grows 10×.
- Contract test: every memory retrieval path applies an identical predicate set (it targets the
  duplication, because the duplication is the defect).
- Screenshots: runs page under load; a malformed trigger quarantined with the tick still ticking; quiet
  hours resolving in a non-UTC zone.

---

## M51 — Bounded work: every unit of work gets a ceiling and a truthful end state

**Changes**
- LLM timeouts, bounded retry budget, per-run wall clock for **every** trigger kind — set at the provider
  port, one place, since the port is unbreached.
- **Provider 429 and deprecation handling** *(uncovered gap)*: rate-limit responses get backoff distinct
  from generic errors; a retired model reference fails loudly at settings-validation time and at call time
  with a message naming the setting, rather than surfacing as an opaque provider error mid-run.
- Run admission control: concurrency semaphore, queue, explicit shed-load response.
- `RunEventBus`: bounded, TTL-evicting, and it stops creating entries on read paths.
- Shutdown: readiness false → stop accepting → drain in-flight within the grace period → mark the
  remainder terminal. The stalled-run reaper extends to all runs, not only ambient ones.
- Transaction restructure (`arch-H8`, `arch-H15`, `code-H3`): claim → commit → external call → write
  back, in the ambient drain and the memory write path. A test that fails when a session is open across
  an `await` on the provider port, so `spec.md:823` is enforced rather than documented.
- Delivery: dispatch-then-commit, attempt counter, bounded retry with backoff, dead-letter state, batch
  limit. Registry cache fails **open** to Postgres.
- Lost-update token totals become an atomic in-database increment (they feed the ambient budget).
- The contradiction sweep keeps the **newest** valid row, not the oldest — with a test asserting drift
  direction.

**Exit criteria**
- Fault injection: provider hangs → runs terminate at the wall clock with a truthful status; provider
  returns 429 → backoff, not failure; Redis killed → served from Postgres with a degraded metric, no 5xx.
- Soak: ambient enabled for an extended run with flat RSS.
- Restart mid-run leaves zero runs in a non-terminal state.

---

## M52 — Untrusted input and secrets

The wave whose failure mode is an attacker steering an autonomous agent that holds tools.

**Changes**
- Fence hardening (`arch-H9`): neutralize the delimiter inside payloads; unguessable per-invocation
  token; applied at the single existing choke point.
- Egress policy for every outbound fetch (A2A card fetch, poll sources, MCP HTTP): allowlist or
  private-range denylist, redirects re-checked per hop, size and time caps, fixed error shape regardless
  of cause.
- XML: `defusedxml`, streamed body with a hard cap enforced during download, parse off the event loop.
- MCP `env`/`headers` become write-only — the A2A `credentials` pattern that already exists one module
  over.
- One exception-text sanitizer, applied before any error is persisted or returned.
- LLM-authored regexes evaluated with a timeout off the event loop (ReDoS).

**Exit criteria**
- An adversarial test per untrusted source — fence escape, SSRF to a private range, billion-laughs XML,
  oversized body, pathological regex — each blocked, each asserted.
- No response body or persisted row contains credential material, asserted across A2A and MCP.

---

## M53 — Deploy and operate

**Changes**
- SSE wire format (`scale-B3`): heartbeat inside the tightest LB default (15 s); monotonic `id:` on every
  event; `Last-Event-ID` resumption; client accumulation idempotent by sequence; HTTP/2 at the proxy so
  the per-host connection limit stops being three tabs.
- Deploy lifecycle (`scale-H1`): bounded `--timeout-graceful-shutdown`; readiness-first drain; polite SSE
  close with a reconnect hint; leader lease released by **awaiting** the cancelled task.
- Readiness/liveness split, container resource limits, restart policy, backend healthcheck.
- Retention for the six unbounded tables — each with its own gate, enforced in-function, per the M48
  §3.7.1 discipline, each covered by the settings-coverage test.
- Observability: §10 labels on metrics (not only logs and spans); LLM latency/error/timeout/429; pool
  saturation; backlog depth; loop errors; in-flight runs as the autoscaling signal.
- MCP reconnection with backoff and a circuit breaker; supervised LISTEN with reconnect and a state
  metric; re-ingest preserves operator intent instead of resurrecting disabled tools.
- Cost model: per-model price table; per-run cost from the usage already captured; a shared spend ceiling
  across all trigger kinds, surfaced in Settings behind an M48-style gate.
- **Backup and restore, actually exercised** *(uncovered gap)*: a documented `pg_dump`/restore
  procedure run against a populated stack, including pgvector index rebuild, with the measured time
  recorded as the RTO figure. Not a design note — a drill.
- **Operator runbooks** *(uncovered gap)*: one page per failure class the reviews identified — pool
  exhaustion, wedged tick, leader loss, provider outage, delivery backlog — each with the metric that
  reveals it and the action that resolves it.
- **Accessibility pass** *(uncovered gap)*: keyboard reachability and labelling on every interactive
  control the Settings and Ambient pages added since M40.

**Exit criteria**
- A rolling deploy with open streams and in-flight runs: zero lost runs, zero duplicated answer text,
  streams resume, leadership transfers within one lease period.
- A restore from backup to a fresh volume serves the same answers; the RTO number is in the doc.
- Screenshots: saturation and LLM dashboards; a stream surviving a deploy; every retention gate in
  Settings.

---

## M54 — Horizontal scale

Where the system stops being one process that happens to run behind a load balancer.

**Changes**
- **Shared control plane** (`arch-C3`): a Postgres-backed run registry with heartbeat and ownership;
  cancellation as a persisted intent the owning replica observes; a persisted job clock so intervals are
  a cluster property, not a per-process one.
- **Delivery fan-out** (`scale-B1`): the leader writes delivery intents; every replica fans out to its
  own subscribers via `NOTIFY` (already in use for cache invalidation). Presence becomes a database-backed
  count across replicas — which also repairs `ambient_pursuit` and stops feeding the M45 salience learner
  a topology artefact.
- **Connection budget** (`scale-B2`): sizing from a declared replica budget; `statement_cache_size=0` for
  pooler compatibility; direct un-pooled connections for LISTEN and the advisory lease. The arithmetic
  published in the operations doc.
- Distributed rate limiter with a bounded key space.
- Cache coherency: read the `generation` counter that already exists; TTLs on every cached blob.
- MCP ingest idempotent under concurrency (`ON CONFLICT`); each replica reconciles its own subprocess
  set against the registry.
- **Indexable memory** (`scale-B5`): per-dimension embedding tables, each a fixed `Vector(d)` with a real
  hnsw index. Keeps §16.1's provider-agnostic dimension strategy — several dimensions coexist — while
  making each indexable. Fresh-install schema; the M46 backfill populates a new key.
- Correct `docs/operations/scaling.md`, which identifies the right requirement and draws the wrong
  conclusion from it.

**Exit criteria**
- Three-replica compose: a run created on replica A is cancelled from B and actually stops; an ambient
  delivery reaches subscribers on **every** replica; consolidation jobs run once per interval
  cluster-wide.
- Load test at N=3 shows throughput scaling and connections within budget.
- Memory recall latency flat from 10k → 100k → 1M memories.
- Screenshots: a delivery reaching two browsers on different replicas.

---

## M55 — The fork seam

**No authentication is implemented here.** What is built is the socket it plugs into — the mechanism
that makes "fork it and add your auth layer" a one-module job instead of surgery in fifty places.

**Changes**
- An `AuthProvider` protocol + registry in `app/auth/`, following the proven `ModelProvider` pattern:
  identity resolution, tenancy predicate contribution, and authorization decision points as explicit
  methods. The default implementation is today's no-op single-user behavior — byte-identical.
- Every tenancy predicate resolves through the port, building on M50's unification. No call site does
  its own `if auth_enabled()`.
- A **contract test suite** any implementation must pass, mirroring the model-adapter contract suite,
  plus a reference stub provider in tests.
- `docs/extending.md`: how to fork, what to implement, what the core guarantees, what it will never do.
- Spec §21 records the seam as a first-class boundary with the same weight as §2.1's provider port.

**Exit criteria**
- The reference stub enforces a fake tenancy rule end-to-end with **zero changes outside its own
  module** — the actual test of whether the seam is real.
- Byte-identity: with the default provider, the full suite passes unchanged.
- A forker can implement the stub from `docs/extending.md` alone.

---

## M56 — Release

The stage that turns a repository into something other people adopt. *(Absorbs the uncovered OSS gap.)*

**Changes**
- `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` (how to report, what is in scope, the auth-is-a-fork
  stance stated plainly), issue and PR templates.
- A versioning scheme and `CHANGELOG.md` reconstructed from the milestone table, then a tagged `v1.0.0`.
- README restructured around the fork-and-extend story: what it is, what it deliberately is not, how to
  run it, how to extend it.
- Full §14 acceptance script including every new step, on a fresh `docker compose up`.
- The M49 load test re-run and published as the performance record against the baseline.

**Exit criteria**
- A person who has never seen the repo can, from the README alone: run it, enable each master, and find
  the extension doc.
- Tag exists, changelog matches the milestone table, ceremony evidence committed.

---

## Sequencing rationale

M49 first because nothing later is measurable without the baseline, and the prompt harness is the
cheapest regression protection available once CI is off the table. M50 before M51 because admission
control and shutdown draining built on process-local state would be built twice. M54 after M51–M53
because a shared control plane is only worth building once work is bounded, deploys are safe, and there
is a signal to prove it worked. M55 late among code stages because a pluggable port over duplicated
tenancy predicates would be a seam over sand — M50 and M54 make it sound. M56 last because release
mechanics should describe what exists.

## Size

| Stage | Effort | Items |
|---|---|---|
| M49 | S–M | 4 |
| M50 | S–M | 5 |
| M51 | M–L | 9 |
| M52 | S–M | 6 |
| M53 | M–L | 10 |
| M54 | L | 8 |
| M55 | M–L | 5 |
| M56 | M | 6 |

Effort: S = hours · M = a day or two · L = a week or more.
