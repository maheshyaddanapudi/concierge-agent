# Production Hardening Program — M49 → M56

One plan, eight stages, each with its own verification gate. Consolidates every finding from the three
reviews in this directory (`architecture-review.md`, `code-review.md`, `scale-review.md`).

**Goal state:** a horizontally-scalable OSS core that a company can fork, implement one port against, and
run as an enterprise system — the Conductor model. Authentication and RBAC are **not built here**; what is
built is the seam they plug into.

**Scope decisions already taken:**
- Auth/RBAC implementation stays out. The *extension point* for it is in (M55).
- Sticky routing is parked. The shared control plane (M54) is the answer instead — sticky was only ever a
  partial mitigation and it makes autoscaling worse.
- §2's "no broker, no queue, no Celery" holds. Every distributed mechanism below uses Postgres, which the
  system already requires. Nothing in this plan adds infrastructure beyond the existing three services.

**Verification discipline** (per CLAUDE.md): every stage states its exit criteria before work starts. A
stage is done when its tests are green *and* its executed proof is captured — test output, load numbers,
curl transcripts, and screenshots where the change is user-visible. Evidence lands in
`docs/acceptance/prod/<stage>/`.

---

## M49 — Foundation: make correctness durable and measurement possible

Nothing else on this list is safe to ship until the suites run automatically and there is a baseline to
measure against.

**Changes**
- `.github/workflows/ci.yml`: backend suite against a Postgres service container, `ruff format --check`,
  `ruff check`, `mypy --strict`, `python -m app.doclint`, frontend `lint` + `tsc --noEmit` + `test`, Docker
  build, and an Alembic upgrade→downgrade→upgrade round-trip. Required check on PRs to `dev` and `main`.
- Enable ruff `BLE` and `S` rulesets; triage every violation that surfaces. The 69 `noqa: BLE001` and 2
  `noqa: S608` markers currently suppress rules that were never enabled — the real violation count is
  unknown until the rules run, and that number is itself a finding.
- Load-test harness (`experiments/load/`) driving the shipped API: concurrent chat runs, concurrent SSE
  subscribers, ambient tick under backlog, memory recall at seeded corpus sizes.
- Capture and commit the **baseline** — deliberately taken *before* any fix, so every later stage has a
  number to beat.

**Exit criteria**
- CI green and required on a PR; screenshot of the run.
- Baseline committed as JSON + a short readme: p50/p95 latency, max concurrent SSE before failure, recall
  latency at 1k/10k/100k memories, connections consumed at rest and under load.
- Ruff `BLE`/`S` violation triage recorded — each remaining suppression justified in one line.

---

## M50 — The ceiling: stop the four ways this falls over first

Every item is a small diff. Together they lift the limits that make all later measurement meaningful.

**Changes**
- **Connection pool** (`arch-C1`): explicit `pool_size`/`max_overflow` from a stated replica budget;
  streaming endpoints take a session, read, and release rather than holding a request-scoped one for the
  life of the stream.
- **Indexes and loading** (`arch-C2` / `code-H1`): add indexes on `runs.conversation_id`, `runs.status`,
  `runs.started_at`, `run_steps.run_id`, `tools.mcp_server_id`; replace `lazy="selectin"` with explicit
  loading at the call sites that need children; paginate `/runs` and `/conversations`; replace
  `len(c.runs)` with an aggregate; give the frontend backoff instead of a fixed 3 s poll.
- **Memory filter unification** (`code-H5`): pinned selection routes through the same predicate builder as
  `recall()`. This is also the first step of M55 — one definition of visibility is the precondition for a
  pluggable auth port.
- **Trigger validation** (`code-H4`): Pydantic models at the API boundary; per-evaluator try/except,
  timeout and error metric in the ambient tick; a repeatedly-raising routine is quarantined rather than
  allowed to wedge the loop.
- **Timezone** (`arch-M4`): a timezone setting; quiet hours and digest times resolve in the user's zone.
  Promoted from Medium — it is small, and "never interrupt you at night" is a promise the product makes
  explicitly and currently breaks for everyone not on UTC.

**Exit criteria**
- Load test vs M49 baseline: ≥50 concurrent SSE subscribers with no pool exhaustion; `/runs` p95 flat as
  run count grows 10×.
- Contract test: every memory retrieval path applies an identical predicate set (the test targets the
  duplication, because the duplication is the defect).
- Screenshots: runs page under load; a malformed trigger quarantined with the rest of the tick still
  ticking.

---

## M51 — Bounded work: every unit of work gets a ceiling and a truthful end state

**Changes**
- LLM timeouts, bounded retry budget, and a per-run wall clock enforced for **every** trigger kind, set at
  the provider port (one place, since the port is unbreached).
- Run admission control: a concurrency semaphore with a queue and an explicit shed-load response.
- `RunEventBus`: bounded with TTL eviction, and it stops creating entries on read paths.
- Shutdown: readiness false → stop accepting → drain in-flight within the grace period → mark the
  remainder terminal. The stalled-run reaper extends to all runs, not only ambient ones.
- Transaction restructure (`arch-H8`, `arch-H15`, `code-H3`): claim → commit → external call → write back,
  in the ambient drain and the memory write path. Add a test that fails when a session is open across an
  `await` on the provider port, so `spec.md:823` is enforced rather than documented.
- Delivery: dispatch-then-commit, attempt counter, bounded retry with backoff, dead-letter state, batch
  limit. Registry cache fails **open** to Postgres.

**Exit criteria**
- Fault injection: provider hangs → runs terminate at the wall clock with a truthful status; Redis killed
  → app serves from Postgres with a degraded metric, no 5xx.
- Soak: ambient enabled for an extended run with flat RSS (proves bus eviction).
- Restart mid-run leaves zero runs in a non-terminal state.

---

## M52 — Untrusted input and secrets

The wave whose failure mode is an attacker steering an autonomous agent that holds tools.

**Changes**
- Fence hardening (`arch-H9`): neutralize the delimiter inside payloads and use an unguessable
  per-invocation token, applied at the single existing choke point.
- Egress policy for every outbound fetch (A2A card fetch, poll sources, MCP HTTP): allowlist or
  private-range denylist, redirects re-checked per hop, size and time caps, and a fixed error shape
  returned regardless of cause.
- XML: `defusedxml`, streamed body with a hard size cap enforced during download, parse moved off the
  event loop.
- MCP `env`/`headers` become write-only, copying the A2A `credentials` pattern that already exists in the
  repo one module over.
- One exception-text sanitizer, applied before any error is persisted or returned.

**Exit criteria**
- An adversarial test per untrusted source: fence-escape attempt, SSRF to a private range, billion-laughs
  XML, oversized body — each blocked, each asserted.
- No response body or persisted row contains credential material, asserted by test across A2A and MCP.

---

## M53 — Deploy and operate

**Changes**
- SSE wire format (`scale-B3`): heartbeat inside the tightest LB default (15 s), monotonic `id:` on every
  event, `Last-Event-ID` resumption from an offset, client accumulation made idempotent by sequence number,
  HTTP/2 at the proxy so the per-host connection limit stops being three tabs.
- Deploy lifecycle (`scale-H1`): bounded `--timeout-graceful-shutdown`, readiness-first drain, polite SSE
  close with a reconnect hint, and the leader lease released by **awaiting** the cancelled task.
- Readiness/liveness split, container resource limits, restart policy, backend healthcheck.
- Retention jobs for the six unbounded tables — each with its own gate, enforced in-function, per the M48
  §3.7.1 discipline, and each covered by the settings-coverage test.
- Observability: §10 labels on metrics (not only logs and spans); LLM latency/error/timeout; pool
  saturation; backlog depth; loop errors; in-flight runs as the autoscaling signal.
- MCP reconnection with backoff and a circuit breaker; supervised LISTEN with reconnect and a state metric;
  re-ingest preserves operator intent instead of resurrecting disabled tools.
- Cost model: per-model price table, per-run cost from the usage already captured, and a shared spend
  ceiling covering all trigger kinds — surfaced in Settings under an M48-style gate.

**Exit criteria**
- A rolling deploy with open streams and in-flight runs: zero lost runs, zero duplicated answer text,
  streams resume, ambient leadership transfers within one lease period.
- Screenshots: dashboard showing saturation and LLM panels; a stream surviving a deploy.
- Every retention job appears in the settings-coverage test.

---

## M54 — Horizontal scale

Where the system stops being one process that happens to run behind a load balancer.

**Changes**
- **Shared control plane** (`arch-C3`): a Postgres-backed run registry with heartbeat and ownership;
  cancellation as a persisted intent the owning replica observes; a persisted job clock so intervals are a
  cluster property rather than a per-process one.
- **Delivery fan-out** (`scale-B1`): the leader writes delivery intents; every replica fans out to its own
  subscribers via `NOTIFY` (already in use for cache invalidation — no new infrastructure). Presence
  becomes a database-backed count across replicas, which also repairs `ambient_pursuit` and stops feeding
  the M45 salience learner a topology artefact.
- **Connection budget** (`scale-B2`): sizing from a declared replica budget, `statement_cache_size=0` for
  pooler compatibility, and direct (un-pooled) connections for LISTEN and the advisory lease so both keep
  working. Publish the arithmetic in the operations doc.
- Distributed rate limiter with a bounded key space.
- Cache coherency: read the `generation` counter that already exists to detect lost-dirty reloads; TTLs on
  every cached blob.
- MCP ingest idempotent under concurrency (`ON CONFLICT`); each replica reconciles its own subprocess set
  against the registry instead of racing to write it.
- **Indexable memory** (`scale-B5`): partition the embedding side-table by `model_key` into per-dimension
  physical tables, each with a fixed `Vector(d)` and a real hnsw index. This *keeps* the provider-agnostic
  dimension strategy §16.1 promises — several dimensions coexist — while making each one indexable, and the
  M46 backfill already knows how to populate a new key.
- Correct `docs/operations/scaling.md`, which currently identifies the right requirement and draws the
  wrong conclusion from it.

**Exit criteria**
- A three-replica compose: a run created on replica A is cancelled from replica B and actually stops; an
  ambient delivery reaches subscribers on **every** replica; consolidation jobs run once per interval
  cluster-wide, not once per replica.
- Load test at N=3 shows throughput scaling and connection count within budget.
- Memory recall latency flat from 10k → 100k → 1M memories (the index doing its job).
- Screenshots: multi-replica delivery reaching two browsers on different replicas.

---

## M55 — The fork seam

The stage that makes the Conductor model real. **No authentication is implemented here.** What is built is
the socket it plugs into.

**Changes**
- An `AuthProvider` protocol + registry in `app/auth/`, following the proven `ModelProvider` pattern:
  identity resolution, tenancy predicate contribution, and authorization decision points as explicit
  methods. The default implementation is today's no-op single-user behavior, so defaults stay
  byte-identical.
- Every tenancy predicate resolves through the port — one definition of visibility, building on M50's
  unification. No call site does its own `if auth_enabled()`.
- A shared **contract test suite** any implementation must pass, mirroring the model-adapter contract
  suite, plus a reference stub provider living in tests that proves the seam works without touching core.
- `docs/extending.md`: how to fork, what to implement, what the core guarantees, what it will never do.
- Spec §21 records the seam as a first-class boundary with the same weight as §2.1's provider port.

**Exit criteria**
- The reference stub provider enforces a fake tenancy rule end-to-end with **zero changes** outside its own
  module — that is the actual test of whether the seam is real.
- Byte-identity: with the default provider, the full suite passes unchanged.
- A written walkthrough a forker could follow, validated by implementing the stub from the doc alone.

---

## M56 — Ceremony

- Full §14 acceptance script including the new steps, on a fresh `docker compose up`.
- The M49 load test re-run and compared against baseline, published as the performance record.
- README restructured around the fork-and-extend story.

**Requires your machine or CI** — image builds do not work in the development container, which is a
constraint on record. Everything before M56 is verifiable from source here.

---

## Sequencing rationale

M49 first because every later fix is unprotected without it and unmeasurable without the baseline. M50
before M51 because admission control and shutdown draining built on process-local state would be built
twice. M54 after M51–M53 because a shared control plane is only worth building once work is bounded,
deploys are safe, and there is a signal to prove it worked. M55 last among the code stages because a
pluggable auth port over duplicated tenancy predicates would be a seam over sand — M50 and M54 are what
make it sound.

## Deliberately not in this plan

- Authentication, authorization, RBAC, SSO, audit logging of access decisions — the fork's job (M55 makes
  it a clean one).
- A message broker, queue, or Celery — §2 holds; every distributed mechanism above uses Postgres.
- Sticky routing — parked as a partial mitigation superseded by M54.
