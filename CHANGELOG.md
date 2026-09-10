# Changelog

All notable changes to the Concierge Agent POC. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); entries are grouped
by milestone (spec §12) instead of semver releases, newest first. **`v1.0.0`** (2026-09-10) is the first tagged release: milestones M1–M56 complete (spec §12). The project
was built spec-first, milestone by milestone, on a single feature branch:
milestones M1–M8 landed via [PR #2] (merged 2026-08-07, superseding the
earlier [PR #1] merge of the M1–M6 line); the HITL card fix landed via
[PR #3].


> **Reconstruction note (M56).** Entries M13–M55 below were reconstructed from the README milestone table when the project was tagged `v1.0.0`; each entry's text is that milestone's row, its date the newest commit in the history that names the milestone. Entries M1–M12 are the original hand-written ones.

## M55 — The fork seam — 2026-09-10

### Added / changed

- The fork seam (PLAN M55 — no authentication is implemented; the socket it plugs into is). An `AuthProvider` port + registry in `backend/app/auth/` following the §2.1 provider pattern: identity resolution, the tenancy predicate contribution (work-row filter, row check, memory visibility fragment), the authorization decision point, the owner stamp and a boot hook; selected by `AUTH_PROVIDER` (default `builtin` — today's §18.8 behaviour, byte-identical dark) with `AUTH_PROVIDER_MODULE` importing a fork's module so its decorator registers it. Every tenancy decision in the core asks the port; a test fails if any file outside the package reads the auth switch. A contract suite runs over every registered provider; the reference stub in `backend/tests/auth_stub.py` — one module, rows shared by tenant, writes gated on `editor` — holds end-to-end through the middleware, stores, streams and memory recall. `docs/extending.md` is the forker's guide; spec §20 records the seam

## M54 — Horizontal scale — 2026-09-10

### Added / changed

- Horizontal scale (PLAN M54 — where the system stops being one process that happens to run behind a load balancer). A shared control plane: every process has a `replica_id` and a heartbeat row in `replicas`, `runs.owner_replica` is stamped at creation, and cancellation is a persisted intent announced on one LISTEN/NOTIFY control channel that the owner acts on at once (its heartbeat is the fallback) — a Stop pressed on any replica stops the run on the one executing it and never writes a status it did not cause; a stream held on a non-owner resolves from the record when the owner announces the terminal transition; boot reaping is scoped to the booting replica and a dead owner's runs are failed truthfully; the consolidation and retention clocks live in `job_clock`, so an interval is a cluster property and a restart re-runs nothing; migrations and seeding take a boot lock. Delivery fan-out: the leader publishes each in-app delivery on the control channel and every replica re-fans it to its own subscribers; the pursuit oracle becomes the cluster audience. The connection budget is declared (`DB_REPLICAS`, `DB_MAX_CONNECTIONS`), checked at boot and served by `GET /replicas`; the pooled connections survive a transaction-mode pooler. A distributed rate limiter, generation-guarded cache coherency with TTLs, idempotent MCP ingest with per-replica reconciliation, and typed per-dimension embedding columns each with a real HNSW index. Compose scales with a host-port range, nginx resolves replicas per request, Prometheus discovers each replica; `docs/operations/scaling.md` rewritten from the evidence. 36 contract tests; §14q-91..96; evidence in `docs/acceptance/prod/M54/`

## M53 — Deploy and operate — 2026-09-09

### Added / changed

- Deploy and operate (PLAN M53 — the wave where the system becomes something an operator can deploy, watch and trim). The SSE wire format survives a deploy: every run event carries a monotonic `id:`, `Last-Event-ID` resumes from it, the heartbeat is inside the tightest balancer default (15 s), a run whose events are gone from the process resolves for a reconnecting client from its row, and the client folds each sequence at most once — a deploy with open streams duplicates no answer text. A readiness-first lifecycle (`deploy.sh`): `SIGUSR1` flips `/ready` to 503 while the port is still open and politely closes the streams the process cannot serve, uvicorn's connection grace is bounded under a 40 s stop grace so the M51 drain always gets its window, the ambient loop is awaited so the leader lease is released at once, `/ready` also reports the database, and compose gains a healthcheck, restart policy and resource limits. Retention for the six tables nothing else ever trimmed, each purge behind its own §3.7.1 gate enforced in-function, previewable and runnable from Settings. Observability that diagnoses: §10 labels on the step metrics, per-call LLM latency and outcome by provider/model from one LangChain callback at the port, pool saturation, in-flight runs, backlog depth, loop errors, MCP and listener state — with Prometheus/Grafana provisioning under `docs/observability/`. MCP reconnection with backoff and a circuit breaker, supervised LISTEN connections, and re-ingest that keeps operator intent. A cost model: per-run cost from captured usage (unknown models reported as unpriced, never guessed), provider-reported prices, operator overrides, and one spend ceiling across every run kind behind its own gate. A backup/restore drill with the measured RTO, one runbook per failure class, and an accessibility pass on the Settings and Ambient controls. 44 contract tests plus 9 client stream tests; §14p-83..90; evidence in `docs/acceptance/prod/M53/`

## M52 — Untrusted input and secrets — 2026-09-02

### Added / changed

- Untrusted input and secrets (PLAN M52 — the wave whose failure mode is an attacker steering an autonomous agent that holds tools). One fence choke point: every untrusted-bearing prompt (remote-agent output, fired-event payloads, delivery bodies, candidate answers, member memories, watch requests, the remembered-context block) is rendered through `app/untrusted.py`, which neutralizes any fence-shaped tag inside the payload and stamps a per-render token on both fence tags — a payload can neither close the fence early nor forge one, and the golden harness pins the tokened prompts. One egress policy (`EGRESS_POLICY` public / allowlist / open) judges every outbound URL fetched on someone else's say-so — A2A cards and calls, poll sources, HTTP MCP servers, the webhook channel — by literal address and by resolution, re-checks every redirect hop in the client's request hook, streams bodies under `EGRESS_MAX_BYTES`, and fails with one fixed shape whatever the cause; feeds parse with `defusedxml` off the event loop. MCP `env`/`headers` are write-only (masked reads, `*` keeps, null removes, `env:VAR` resolves at connect time). One sanitizer redacts known secret values and credential shapes before any error is persisted or returned, and on every log line. Authored regexes pass a static guard at the API and before every match, which runs under a timeout off the loop. 40 contract tests; §14o-77..82; evidence in `docs/acceptance/prod/M52/`

## M51 — Bounded work — 2026-09-02

### Added / changed

- Bounded work (PLAN M51 — every unit of work gets a ceiling and a truthful end state). Limits live at the provider port: `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` reach every adapter through one function, a contract test asserts each adapter carries them, and a provider failure reaches the run as a classified error (rate-limited / timeout / unknown-or-retired model / provider error) naming the model and the setting that resolved it; a retired model is refused at validation. Every run has a wall clock (`run_wall_clock_s`) and a heartbeat, and the stalled-run reaper now covers chat runs too. Admission is explicit: `run_max_concurrent` semaphore, `run_queue_max` queue with a visible `queued` status, chat shed with 503 + `Retry-After`, `GET /ready` as the readiness gate. Shutdown drains in-flight runs for `SHUTDOWN_GRACE_S` and restart reaps anything still `running`/`queued` as failed "orphaned by a restart" with its open steps cancelled. The run event bus is bounded and TTL-evicting. No session spans a provider call: the ambient drain claims → commits → processes → writes back (abandoned claims reclaimed after 10 min), memory writes, digests, exemplars and compaction embed between sessions — enforced by a per-task session tracker the fake provider checks in strict mode, so a regression fails the suite. Delivery dispatches then commits; external sends carry an attempt counter, backoff (60 s → 5 min → 30 min) and a dead-letter state with a per-tick retry stage. The registry cache fails open to Postgres with a degraded counter; token totals increment atomically; the contradiction sweep keeps the newest fact. 29 contract tests; §14n-70..76; fault-injection evidence in `docs/acceptance/prod/M51/`

## M50 — The ceiling — 2026-09-01

### Added / changed

- The ceiling (PLAN M50 — the four ways the M49 baseline showed a fresh install falls over first, each fixed at its cause). The connection budget is explicit (`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT`) and `/chat/stream` releases its session before streaming, so an open tab holds no pooled connection (the baseline failed the pool at 15 tabs). `/runs` and `/conversations` are paged with `X-Total-Count`, `run_count` is an aggregate, child relationships are `lazy="raise"` and loaded explicitly where a detail view needs them, the five missing hot-path indexes ship in one migration, and the UI polls with backoff (3 s while something is live, 15 s when quiet, never in a background tab). One memory visibility predicate (`visibility_sql`) feeds recall's two legs and the pinned profile — the pinned path had leaked project rows across projects and never checked the owner; the contract test spies on the builder so a rule cannot be added to one path and forgotten in the other. Routine triggers are typed at the API boundary (interval ≥ 60 s, parseable cron, ISO `once.at`, webhook filters with known ops and compiling regexes), the schedule evaluator isolates routines and quarantines one whose trigger keeps raising (`status='error'` after three, reason recorded), and every tick stage runs under a timeout with an error counter so one failure never skips the rest. `ambient_timezone` makes quiet hours and digest times wall-clock in the user's zone (UTC default = byte-identical). 20 contract tests; §14m-67..69

## M49 — Production-hardening foundation — 2026-09-01

### Added / changed

- Production-hardening foundation (`docs/research/prod_hardening/PLAN.md` M49): measurement before fixes. The prompt regression harness — every prompt file has a golden set rendered the way its consumer renders it and graded by the spec §15 grader, so a dropped binding sentence, a renamed placeholder, or a prompt no code loads fails `python -m app.prompts.check` (pytest gate + Docker build gate; it found and removed the consumer-less `answer_ui.md`). The load harness (`experiments/load/`) drives the shipped API and the baseline was captured before any fix — read-path latency, `/runs` under 10× growth, concurrent chat runs, the SSE subscriber ceiling, recall by corpus size with the vector leg's plan, ambient backlog drain, connection peaks — so M50, M54 and M56 have a number to beat. Ruff `BLE`/`S` enabled with all 41 violations triaged: 31 runtime asserts replaced by explicit checks, every surviving suppression justified in one line, `defusedxml` for the RSS body. Evidence: `docs/acceptance/prod/M49/`

## M48 — The switchability rule — 2026-08-30

### Added / changed

- The switchability rule (spec §3.7.1 — from an independent pre-public audit that traced every gate to its enforcement site rather than trusting the spec's intent). The audit found six behaviors the system performed on its own with no switch of their own: the four memory consolidation jobs (decay expires rows, contradiction quarantines them, communities spends a model call per changed group, and compaction hard-deletes — four different consequences, so one family switch would not have done), the anticipation job (the only feature that initiates contact unprompted — silence had to be statable, not just learnable via the hit-rate floor), and the §15 eval surface. All six now have named gates, every default equal to the behavior it replaces, so the promotion is byte-identical. Plus the §3.7.1 corollary — a setting that reads as off must be off: `memory_community_budget_tokens = 0` now skips the rebuild instead of silencing injection while the job kept spending tokens, and the Settings page labels the legal-but-degraded forgetting-without-an-embedding-model case instead of leaving it silent. Settings coverage closed to 89/89 and asserted by test, so a future key with no control fails the suite rather than a review; dead `STALL_AFTER_S` removed. 15 contract tests; §14k-61..63

## M47 — Extraction tuner — 2026-08-30

### Added / changed

- Extraction tuner (spec §17.7/§16.2: the second feedback consumer — the tombstone-informed learner the M44 no-consumer note reserved. Deterministic rules over machine-write tombstones (with confidence-at-admission metadata) and quarantine review rejections, machine sources only — the human's own words are consent, never a training signal. Kind routing sends a ≥50%-repudiated kind's future machine writes through the review queue (novel junk of a repudiated kind is what tombstone suppression cannot catch); the admission floor — promoted to the live `memory_admission_min_confidence` setting, byte-identical default — walks ±0.05 in [0.5, 0.9] on a band-local trigger, because the harness showed a raw forget-rate trigger ratchets into starving valuable kinds. Two-world harness evidence: world A learner 10 junk admissions at zero valuable-blocked vs 42–60 for every zero-loss static; world B floor walks 0.5→0.60, stops at the zero-collateral point, beats the shipped default 36 vs 66 — but NOT the retrospective oracle static (12), a failure reported at full prominence rather than reworded: a single-dial learner converges to its dial's oracle, it cannot beat it in-window. Gate `memory_extraction_learning` off\|propose\|auto, default off — born dark; 17 contract tests; §14j-59..60)

## M46 — Embedding backfill job — 2026-08-29

### Added / changed

- Embedding backfill job (spec §16.2: the promised "re-embeds in the background and flips" scheduler job, built — an advisory-locked hourly job embeds every live memory, run digest, and active plan exemplar lacking a vector under the ACTIVE model key, batched and pass-bounded, old-key rows coexisting untouched, write-through failures repaired by the same path; closes the known gap recorded in stage 32 where a row without an embedding silently degraded the forget gate to hash-only matching. Tombstones deliberately excluded — they keep no text, so pre-switch tombstones stay on hash+anchor matching: privacy over recall, stated in the spec rather than discovered later. 10 contract tests; §14j-58)

## M45 — Salience tuner — 2026-08-30

### Added / changed

- Salience tuner (spec §17.7: the first consumer of the M43b `judge_reward` ledger — deterministic rules, not a bandit (salience decisions are rare events): per-category mutes as `salience:<cat>` policy rows (revert un-mutes, M44 reject stays inert, review UI works day one) and urgency-floor moves ±1 clamped [2,5] through the same `_apply_special` path as the digest-time learner; own gate `ambient_salience_learning` off\|propose\|auto, default off — born dark, byte-identical until a human flips it. Evidence-first on the M24-pattern harness: learner precision .655 vs best-static .622 and default .483 at zero missed-critical and zero clamp violations, total judge reward +17 beating every static point; honest dynamics (the post-mute floor slide) and the harness-forced mute-rule change (≤0.10, not zero) recorded in `docs/research/feedback_loop/report.md` rather than tuned away. 13 contract tests)

## M44 — Durable forgetting + feedback-trace completeness — 2026-08-30

### Added / changed

- Durable forgetting + feedback-trace completeness (spec §16.1/§16.2/§17.7/§8.8: the M43c audit's finding made correct — physical delete + existence-only reconciliation meant the system could quietly RE-LEARN a fact the user deleted. Deletion now splits into Forget (metadata + normalized-hash + payload-token-hash tombstone, embedding copy for suppression only, destroyed with the tombstone) and Erase (physical, no trace — privacy by explicit choice; purge clears tombstones too); the §16.2 admission gate refuses suppressed candidates via the hybrid gate — threshold cosine alone, or gray-band ≥0.70 with a shared distinctive-payload anchor — calibrated by LIVE measurement: two real paraphrase pairs at cosine 0.876 and 0.847 proved no single threshold separates restatements from value-updates; user re-assertion overrides in one step; the Forgotten tab lists tombstones metadata-only with working Unforget; §17.7 pending proposals gain explicit reject; overlap-guard overrides logged content-free. `memory_forget_enabled` default false = byte-identical; 17 contract tests; §14i-55..57 proven live through four campaign legs whose two failures each produced a spec-recorded correction)

## M43 — Salience decision surface + settings completeness — 2026-08-30

### Added / changed

- Salience decision surface + settings completeness (spec §17.5/§8.9/§8.7: M42 shipped two promises its own spec text made and its code did not keep — `propose` "queued verdicts for approval" with nothing able to approve them, and §8.7 listed a salience model override that had no picker. A verdict now renders on its own delivery card leading with the CONSEQUENCE in plain language ("Worth your attention" / "Worth remembering" / "Looks like noise") with Do it / Leave it, and a layered "why this?" that never omits that a model made the call; every applied verdict — human- or `auto`-applied — carries a working Undo that restores the pre-mutation snapshot and retracts only the memories retention itself created, refusing honestly once a digest has spent the escalation rather than pretending to un-send it; apply and decline write the judge's OWN reward (`judge_reward` on the salience record) — deliberately separate from the delivery's §17.7 `accepted`/`dismissed` feedback, because "the judge misread this alert" and "this alert was worthless" are different facts and undoing an over-eager escalation of a real alert must never feed the §17.3 precision rule toward demoting the category — so the judge finally accrues the evidence by which it can be evaluated instead of merely trusted; decisions are first-write-wins, conflict-refusing and tenant-scoped. Plus the §8.7 rule — every §3.7 role model has a Settings picker in the section owning it — closing `memory_extraction_model` and `ambient_salience_model`, both API-validated and unreachable until now. 12 new contract tests; §14h-52..54 proven live)

## M42 — Delivery salience + truthful delivery record — 2026-08-29

### Added / changed

- Delivery salience + truthful delivery record (spec §17.5/§18.4/§16: the delivery EVENT and the delivered CONTENT are different facts — `in_app` becomes a first-class ledger entry written only when a real-time broadcast reached nobody (a digest flushing to an empty room is normal, not a failure), and `seen_at` + an unread nav badge make attention a fact rather than an inference; the salience pass then re-judges what nobody saw — deterministic prefilter (tier, urgency floor, and `skey` recurrence, a signal supersede-collapse had been discarding since M23) then a fail-open LLM judge over the FENCED body — into three ledgered outcomes: escalate to digest-lead (never a re-interrupt, never breaking quiet hours), retain into §16 through the normal admission path with delivery provenance, or drop on the explicit record. `ambient_salience_mode` default `off`, so defaults stay byte-identical; §14g-48..51 proven live plus a randomized regression sample of archived frames)

## M41 — Ambient pursuit — 2026-08-28

### Added / changed

- Ambient pursuit (spec §17.5/§18.4: channel routing was presence-blind — a configured email on `interrupt` sent whether or not the toast had already landed in front of you. `ambient_pursuit` ('off'\|'away'\|'always', default 'always' = pre-M41 behavior, so defaults stay byte-identical) now gates the EXTERNAL half of `dispatch_delivered` on whether the in-app half reached anyone; the presence oracle is `stream_subscriber_count()` sampled immediately before `_publish` — not an estimate of presence but the literal audience of the toast being sent, which stays correct per-process under §18.9 multi-replica and avoids the idle timer's false positives against an open, watched tab; a held escalation logs `ambient_pursuit_held` and leaves an ABSENT ledger entry rather than a silent one; strictly subordinate to tiers, quiet hours, and the notification budget — it escalates the channel, never the hour; Settings select beside the routing it modifies — 12 contract tests incl. the full tri-state × presence matrix, and §14f-45..47 proven live against local SMTP + SMS-gateway-shaped webhook sinks)

## M40 — Config hardening + per-chat target pin — 2026-08-30

### Added / changed

- Config hardening + per-chat target pin (spec §3.7/§7.5/§8.7: the composer's direct-invocation pin — and its history-summary checkbox — became per-conversation state (a conversation-keyed map; `?target=` deep links pin only the chat they open, new chats always start at auto); `a2a_poll_interval_s` wired as a tick-bounded monotonic watermark in the parked-task poller (effective cadence `max(tick, interval)`); seven hardcoded constants promoted to live validated settings with defaults equal to the constants they replaced — `ambient_tick_interval_s`, `rate_limit_burst`/`rate_limit_per_s`, `overlap_threshold_percent`, `run_stall_after_s`, `agentic_recursion_limit`, `a2a_http_timeout_s`, `a2a_fence_max_chars` — plus `AUTH_SESSION_TTL_H` env; the Settings page gained Ambient (§17), A2A (§19), and API-guardrail sections with live nav toggling and per-control inline 422s; §14e steps 41–44 proven live (evidence in `docs/acceptance/28-config-hardening/`) with the affected settings frames surgically recaptured; the campaign also fixed two silent-failure UI defects — per-control settings 422s that never surfaced, and the skill editor's §4 overlap check 422ing invisibly on an extra payload field)

## M39 — A2A long-running tasks — 2026-08-27

### Added / changed

- A2A long-running tasks (spec §19.6: budget expiry PARKS the remote task instead of erroring — ambient on, under `a2a_max_parked` (0 disables parking, timeout becomes a plain tool error) — and the run completes honestly with a "result will be delivered ambiently" note; the ambient leader tick gains `poll_parked_tasks()` — rechecks each parked row via `tasks/get`, terminal outcomes deliver through the §17.5 outbox (`category='a2a'`, `skey=a2a:{row}` supersede lineage, tier 1 + urgency 4 for failures, tier 2 for results, fenced bodies) with zero recheck runs ever; a remote question while parked lands a tier-1 "needs your input" delivery pointing at the task drawer; the Remote Agents page gains that drawer — live task list with reply box for input-required (`POST .../tasks/{id}/reply`: terminal→outbox delivery, still-working→re-park, another question→stays in the drawer) and cancel (`POST .../tasks/{id}/cancel` propagates `tasks/cancel`); poller inert while a2a dark — 5 contract tests incl. park→poll→deliver with zero new runs and the parked-then-ask drawer round-trip)

## M38 — A2A execution in runs — 2026-08-27

### Added / changed

- A2A execution in runs (spec §19.5: `kind='a2a'` tools materialize as lazy call-time proxies — dark/dead backends are tool-call errors with error-edge semantics, never rebuild triggers; adopt-or-send replay idempotency keyed on `(run_id, call_key)` so HITL resume re-execution ADOPTS the open remote task instead of re-sending (§7.1 spin_worker contract); remote `input-required` raises the standard HITL interrupt with the question marked "untrusted, its own words" — deny cancels remotely, approve replies into the same remote task; every remote result and error body wrapped in the `<untrusted_remote_agent_output>` fence before entering any model context; run Stop propagates `tasks/cancel` best-effort via a detached cleanup task; `submitted/working` drains through a 1s `tasks/get` settle loop under the `a2a_task_timeout_s` budget — 6 contract tests through the REAL run machinery: echo round-trip with fence, HITL ask→approve and ask→deny, failed-terminal error edge honestly reported, Stop cancel propagation)

## M37 — A2A substrate — 2026-08-27

### Added / changed

- A2A substrate (spec §19.1–19.4: `remote_agents` registry as an MCP-server peer — register by card URL, the manager fetches `/.well-known/agent-card.json` via a2a-sdk 0.3, stores the card, projects per-card-skill `kind='a2a'` tools with MCP ingest semantics (refresh-in-place, inactive-on-vanish, collision-suffixed `tool_key`), periodic card refresh honoring `a2a_card_refresh_interval_s`; auth read off the card's `securitySchemes` at runtime — apiKey header/query/cookie, http basic/bearer, oauth2 client_credentials via authlib with a skew-aware token cache, placed by a standalone `ClientCallInterceptor`; credentials WRITE-ONLY in the DB with `env:VAR` indirection, never serialized outward, per-scheme `configured` flags + `auth_status` computed instead; dark by default — `a2a_enabled=false` means 409 writes, inert tools, byte-identical runs; Remote Agents admin page with card/skills/auth chips + write-only credential editor — 19 contract tests incl. the full auth placement matrix against a scripted SDK-server stub)

## M36 — Full acceptance ceremony — 2026-08-26

### Added / changed

- Full acceptance ceremony (spec §18.10: fresh volumes via `./decom.sh -y` + fresh `docker compose up` on qwen3.8-max, then the original §14 eleven-step script re-earned end-to-end — seed → UI-registered MCP server → custom skill → exposure toggle → branch/error/HITL sub agent with inline validation → multi-turn chat with mid-run HITL + history follow-up → uncovered-ask fallback rung → kill-server error-edge + reconnect → trace/cancel/retry → planner-label + second-provider (gemini-3.6-flash) switch + purge → agentic + mid-session tool live-sync; plus §14c ambient UI + decision plane live (typed builder, webhook fire matched/held, live qwen watch compile, correlation chain, run history), an adversarial fire proven fenced, a live custom-gateway smoke with usage metadata, and the §11 byte-identity/dark-mode suites — 66 UI frames + transcripts in docs/acceptance/ceremony_m36; full backend suite 691 passed, 1 skipped)

## M35 — Multi-replica ambient coordination — 2026-08-26

### Added / changed

- Multi-replica ambient coordination (spec §18.9: the tick elects a leader through a Postgres SESSION advisory lock on the dedicated pair `(427017, 1)` held on an unpooled connection — the session IS the lease, renewal is a per-tick liveness check, and process death releases the lock server-side; only the leader runs the evaluators, every replica LISTENs + drains (the SKIP-LOCKED drain/executor were replica-safe by construction), a dark loop holds no lease, `concierge_ambient_leader` gauge per replica; proven in-process with two concurrent loops — exactly one ticks, both drain, takeover on leader stop — AND live with two containers on one database: failover in 48s and re-acquisition in 51s, both ≤ one 60s tick; compose stays three services, scale via `--scale backend=N`; evidence in docs/acceptance/coordination_m35)

## M34 — Auth + tenancy + hardening — 2026-09-03

### Added / changed

- Auth + tenancy + hardening (spec §18.8: `AUTH_ENABLED` env gate — DARK BY DEFAULT, auth off is byte-identical single-user; scrypt passwords + bearer sessions sha256-hashed at rest (24h TTL), bootstrap admin one-time password printed once at boot; AuthMiddleware over `/api/v1` with exemptions (health/metrics/login + the token-auth routine fire — the fire token IS the auth; SSE accepts `?token=` since EventSource can't set headers); admin-gated registry/settings writes, token-bucket rate limit (burst 120, 10/s — proven live: 200 hammered requests → 112×200 + 88×429), security headers + CORS pin; tenancy: `user_id` on all eight work tables, strict `scope_to_user`/`owns_row` on every list/detail API, run tasks re-bind the owner so ambient + eval work scopes to the routine/intent owner, per-user delivery buckets/quiet-hours/digest-times/tier-overrides/precision/learner partitions and presence rows; §14c-32 proven live — bootstrap admin + member, real-qwen run per identity, runs/routines/deliveries invisible across users both ways, member registry write 403, fire-token-only fire became a member-owned run + delivery, LoginGate UI, then auth off reopened everything; evidence in docs/acceptance/auth_m34)

## M33 — Custom gateway adapter — 2026-08-27

### Added / changed

- Custom gateway adapter (spec §18.7: `custom` provider — OpenAI-compatible chat-completions behind env-only `CUSTOM_GATEWAY_BASE_URL`/`_API_KEY`, model list from `CUSTOM_GATEWAY_MODELS` (the env list IS the validated list — off-list refs reject at save); explicit `effort` params rejected at validation, internal role-default effort hints dropped at call time; registered like every provider, shared adapter contract suite green, zero changes outside `app/llm/`; proven live — `get_model("custom:qwen/qwen3.8-max")` answered through a real gateway with usage metadata, and a full chat run completed with `default_model=custom:…`)

## M32 — Evals — 2026-08-25

### Added / changed

- Evals (spec §15 promoted: csv/xlsx dataset upload in the predefined format; admin-direct batch runner over the EXISTING run machinery — skill cases run a single-skill ephemeral worker by registry id, sub-agent cases ride §7.5 direct, both exempt from the rung-4 exposure gate; every case is an ordinary Run with `is_eval=true` + `eval=true` in the log label set, HITL auto-approved; graders exact/contains/llm_judge with structured verdicts, judge failure ⇒ `error`; eval_datasets/cases/runs/results tables + config snapshots; LangSmith publish when configured; Evals UI page + skill/sub-agent drawer launchers; §14c-31 proven live — 3/3 passed on qwen across all three graders, evidence in docs/acceptance/evals_m32)

## M31 — Memory communities — 2026-08-27

### Added / changed

- Memory communities (spec §18.6: label propagation over `memory_entity_links` with deterministic tie-breaks as an hourly consolidation job; `memory_communities` rows keep a member-set signature so only CHANGED communities re-summarize (extraction model, fail-open keeps the old summary); recall gains community breadth under its own `memory_community_budget_tokens` line — proven live: qwen summarized a 3-entity meridian/kafka/clickhouse cluster and the summary injected for a partial-recall probe, chat answered with all facts + memory citations; live proof also found+fixed a real recall bug — raw `SELECT *` positional column mapping broke on migrated DBs whose column order drifts from the model, replaced with ORM loads)

## M30 — Ambient UI completeness — 2026-08-25

### Added / changed

- Ambient UI completeness (spec §18.5: typed trigger builder — schedule kind pickers + §17.3 webhook filter rows — beside the raw-JSON escape hatch; routine drawer run history via `GET /runs?routine_id=`; ledger rows expand into the correlation-chain view + per-category precision sparklines; watch authoring from the page — `POST /watches/compile` reuses the `ambient.watch` compiler (live qwen picked the M28 `pending_hitl_count` probe), typed event-filter watches via `POST /watches`; decision-plane fix: webhook fires now match the routine's STORED webhook-trigger filters — proven live: matching fire ran, non-matching held; evidence in docs/acceptance/ambient_ui_m30)

## M29 — Delivery channels — 2026-08-28

### Added / changed

- Delivery channels (spec §18.4: adapter registry behind `ambient_channels` per-tier routing — `in_app` always, `email` renders a digest batch as ONE SMTP message, `webhook` POSTs a gateway-shaped JSON envelope; per-channel send ledger `external` on every delivery row; failures ledgered + logged, never blocking the outbox; global `/api/v1/ambient/stream` SSE — 409 when dark, self-closing on dark — and the in-app tier-0/1 toast; §14c-30 proven live: one 12-item digest email at a local SMTP sink, interrupt toast with no reload + webhook envelope, evidence in docs/acceptance/ambient_channels_m29)

## M28 — Real trigger sources — 2026-08-25

### Added / changed

- Real trigger sources (spec §18.3: parameterized contracts `fn(watermark, config)` / `fn(config)→float`; native `http_json`/`rss`/`mcp_tool` poll sources + `workspace_disk_pct`/`pending_hitl_count`/`runs_failed_last_hour` probes, boot-registered with config shapes the watch compiler lists; `WatchCompile` gains `poll_config`/`probe_config`; §14c-29 proven live end-to-end — qwen compiled an `http_json` watch over a real feed conversationally, the poller ingested a real item, the fire produced a run + tier-2 delivery; live proof also caught+fixed a real decide bug: poll-item filters now match item fields)

## M27 — Memory context pack — 2026-08-25

### Added / changed

- Memory context pack (spec §18.2: routine `include_memories` — fires share ONE persistent conversation, proven live: Beat #2 quantified the delta vs Beat #1 on qwen3.8-max; `project` memory scope with key-partitioned recall/injection that never leaks across projects; the aggregator gains the §16.3 remembered-context block)

## M26 — Ambient completeness pack — 2026-08-25

### Added / changed

- Ambient completeness pack (spec §18.1: per-routine `model_ref` honored end-to-end — explicit role models > routine override > default, proven live with a kimi-k3 routine on a qwen stack; near-due poller tightening; escalation budget on digest approvals; per-item anticipation deliveries; learner threshold recovery; independent multi-slot digest shifting; judge `usage_metadata` accounting — judge_live battery: 7 calls, 3,880 in / 1,609 out tokens at Set-F1 1.0)

## M25 — Adaptive policy learning — 2026-08-30

### Added / changed

- Adaptive policy learning (spec §17.7: reward-weighted bandit over the delivery substrate — category re-tiering both directions with a hard tier-1 floor, digest-time shifts ≤2h from a ledgered anchor, per-intent judge thresholds; `ambient_learning_mode` off/auto/propose with auto first-class — applies immediately under clamps, ledgered + one-click revert; gate passed: learning 0.70 vs static 0.20 intervention precision, zero learner tier-0 escalations; §14c-28 proven live tick-driven in both modes)

## M24 — Ambient evals — 2026-08-30

### Added / changed

- Ambient evals (spec §17.6: simulated-clock scenario harness — Set-F1 1.0 with the qwen3.8-max judge vs 0.57 filters-only; guard battery: dedupe/depth/kill-switch hold under stress; 3-sim-day soak: AIMD 10.8× cheaper than fixed polling, 2/day digests exact; 8-min live soak: 8/8 fires→completed runs, 0 stalled, supersede-collapse live; report in docs/research/ambient/07)

## M23 — Ambient delivery plane + §8.9 UI — 2026-08-30

### Added / changed

- Ambient delivery plane + §8.9 UI (spec §17.5/§17.6: four-tier outbox flushing with interrupt budget + quiet hours + bounded deferral + digest builder + return-flush + supersede-collapse; feedback → blended reward substrate; rule-based precision auto-downgrade on an append-only policy ledger; anticipation job with hit-rate self-prune; four-tab Ambient page)

## M22 — Ambient execution plane — 2026-08-25

### Added / changed

- Ambient execution plane (spec §17.4: fires become ordinary runs with trigger provenance + narrowed projection + budgets + abstain; `ambient.wakeup`/`ambient.cancel_wakeup` with clamps/caps/done-guard; `ambient.watch` compile-echo-confirm; H3 heartbeat/reaper; HITL timeout → digest)

## M21 — Ambient trigger + decision planes — 2026-08-25

### Added / changed

- Ambient trigger + decision planes (spec §17.2/17.3/17.3a: schedules with catch-up watermarks, AIMD pollers, state-edge conditions, three-tier fire/hold gate with significance judge, CEP-lite patterns with armed-timer absence)

## M20 — Ambient substrate — 2026-08-26

### Added / changed

- Ambient substrate (spec §17.1/17.2: event store with cascade guards, routines + hashed fire tokens, NOTIFY-wake drain, presence + real idle detector — dark by default)

## M19 — OpenRouter gateway adapter — 2026-08-25

### Added / changed

- OpenRouter gateway adapter (spec §2.1 custom-gateway scenario) + six-model cross-provider retest matrix

## M18 — Closed-loop refinement — 2026-08-27

### Added / changed

- Closed-loop refinement (spec §16.7: citation feedback — only cited memories reinforce; digest compaction — episodic store stays O(conversations); entity-hop recall; 90-day time-warp simulation)

## M17 — Consolidation — 2026-08-30

### Added / changed

- Consolidation (spec §16.6: decay sweep, generative reflection with evidence citations, contradiction sweep, advisory-locked jobs) + experiment harness

## M16 — Procedural layer — 2026-08-30

### Added / changed

- Procedural layer (spec §16.5: plan exemplars with vote lifecycle, routing stats, fallback mining → inactive skill proposals)

## M15 — Semantic layer — 2026-08-20

### Added / changed

- Semantic layer (spec §16.4: extraction pipeline, LLM-match/code-resolve reconciliation, instruction quarantine, memory tools + Memory UI)

## M14 — Episodic layer — 2026-08-20

### Added / changed

- Episodic layer (spec §16.3: run digests, conversation rollups, prompt-assembly injection with budgets + data-fencing)

## M13 — Memory substrate — 2026-08-26

### Added / changed

- Memory substrate (spec §16.1: pgvector store, bi-temporal supersession, admission gate, hybrid recall, settings — dark by default)

## M12 — Declarative .agent.md sub-agents — 2026-08-09

### Added

- **`.agent.md` (spec §3.4)**: a third authoring path onto the same
  sub_agents registry row — YAML frontmatter (name, description, persona,
  model/model_params, direct_exposure, §3.5 workflow) + a documentation
  body. Skill nodes reference skills by NAME; the seed pass resolves them
  to registry uuids, validates with the same structural + factory-compile
  checks the API applies at save, and upserts keyed on (name, static) with
  file provenance in native_ref.
- **Lifecycle**: invalid files land as status='error' (UI-visible, logged,
  never crash boot); a fixed file flips error→active; a removed file marks
  its row inactive (never deletes); user status/direct_exposure toggles
  survive reseeds while definition fields always follow the file.
- **Seeded example**: workspace-reporter.agent.md — audit(workspace-auditor)
  → form gate (report format + free-text addendum) → write(file-ops), with
  an empty-workspace branch; ships direct_exposure=true, so every §7.5
  surface works on a file-defined agent out of the box.
- 9 tests: parser rejections, seed resolution + static rules + form-gate
  direct invocation, and the full reseed lifecycle (toggle survival,
  error→active recovery, file-removal deactivation, malformed-file skip).

## M11 — Opt-in history summary for direct invocations — 2026-08-09

### Added

- **`include_history_summary` (spec §7.5)**: direct runs stay cold by
  default; the flag is the one sanctioned way to hand a pinned sub agent
  conversational context — restoring the translator role the planner plays
  for routed dispatch. One summarization call (default model, effort low,
  prompt `app/prompts/history_summary.md`, the planner's capped window),
  recorded as a `summary` step with usage rolled up; the worker receives
  the summary block + the user's verbatim message; fail-open to the cold
  task. Checkpointed task → HITL resume never re-summarizes; retry
  preserves the flag (`runs.include_history_summary`, migration
  `d4f7b2c8e1a9`). Gating: 422 on `/chat` without a target (the
  orchestrator always gets history), 422 on `/invoke` without a
  `conversation_id` (nothing to summarize).
- **Composer checkbox** shown only while a sub agent is pinned AND the
  conversation has a completed run; summarized direct bubbles carry a
  `+ctx` marker.
- Stage 27 acceptance evidence: visibility rules, cold-vs-context
  side-by-side (the cold run cannot recall a number; the context run can),
  the traced summary step, and both 422 gates — plus stages 25/26/12
  re-captured with the checkbox present.

## M10 — Direct sub-agent invocation — 2026-08-09

### Added

- **Direct invocation (spec §7.5)**: a sub agent with `direct_exposure=true`
  can be pinned to handle a request without the planner. Four surfaces, one
  path: `POST /sub-agents/{id}/invoke` (`{message, conversation_id?}` →
  `run_id`), `POST /chat` with `target_sub_agent_id`, the Sub Agents page
  "Invoke →" row action, and the chat composer's target picker
  ("Orchestrator (auto)" + every active exposed agent, with a visible pin
  chip). Every surface creates a persisted run with
  `orchestrator_mode='direct'` + `target_sub_agent_id`.
- **`sub_agents.direct_exposure`** (migration `c9e1f5a2d7b8`): mirrors the
  tools/skills flag — togglable on static records, `direct` chip in the
  table, toggle on both the custom editor and the native card. Static seeds
  ship exposed; the migration backfills existing static agents.
- **`direct` orchestrator mode**: a one-node graph on the run's checkpointer
  thread reuses the ladder executor (`resolve_capability` +
  `execute_resolution`), so native and custom agents run the exact worker
  code paths routed dispatch uses — HITL pause/resume, step recording, and
  a pinned `route` step (rung `native_sub_agent`/`custom_sub_agent`) for
  trace parity. The shared runner tail applies unchanged: formatter on →
  full `answer_ui` treatment; off → raw markdown. Gating (active + exposed)
  is enforced at the API (403/409) and re-checked at execution start;
  `retry` on a failed direct run preserves the pin.

### Changed

- Chat user bubbles for direct runs carry a `→ agent · direct` marker; the
  Runs page mode badge shows `direct`. The Sub Agents page "Test invoke"
  action (message-prefix hint) is replaced by real pinning via `/?target=`.

### Added (seeded native tier)

- **Two new native skills over previously-untagged tools** (spec §9):
  `workspace-auditor` (directory_tree, list_directory_with_sizes,
  search_files, get_file_info — read-only workspace mapping) and
  `workspace-curator` (create_directory, move_file, read_multiple_files —
  tidy, never delete).
- **`workspace-warden`, the first seeded native sub agent** (spec §3.4): a
  hand-written two-stage LangGraph (`audit → curate`) over both skills. The
  graph is code (factory bypassed for construction) but each stage delegates
  to the factory's skill-node semantics — scoped tools, model resolution,
  middleware stack identical to factory-built workers. Registered with
  covered skills by NAME; the seed pass resolves names to registry uuids
  (`_resolve_covers`). Ships exposed, so all four §7.5 direct-invocation
  surfaces work on the native tier out of the box.

## M9 — The formatter: A2UI-first structured answers — 2026-08-08

### Added

- **The formatter role** (spec §7.1): an explicit presentation role beside
  planner/aggregator, with its own Settings section — on/off (off = the
  call never runs, raw renders directly, no artifact exists), model +
  effort (`formatter_model`, null → default model), presentation
  (`a2ui_first` default | `raw_first`), charts toggle, and a user-visible
  coverage flag threshold. Conditional UI: the options exist only while
  the formatter is on.
- **Transformation prompt** (`prompts/formatter.md`): replaces the old
  summarizer with a binding parity contract — preserve every fact,
  number, warning, recommendation; drop only duplication; prose stays in
  markdown `text` components — plus explicit negative examples.
- **Artifact-driven, run-time-frozen rendering**: each artifact carries
  its own `presentation` and `coverage`; history renders by what
  happened at run time, never by current settings. No artifact → raw
  only, no structured toggle. Live runs stream raw tokens and settle
  into their arrangement when the artifact lands.
- **Deterministic coverage metric**: numbers/URLs/code-span retention
  computed in code per artifact, shown as a quiet badge (amber under the
  threshold) — an instrument, never a render gate.
- **Formatter-independent charts**: `render_chart` tool output is
  persisted on `runs.charts` (new column + migration) and rendered with
  the primary answer in every formatter state; tool names now persist on
  trace steps.

## Post-M8 fixes — 2026-08-07

### Fixed

- Never leave a HITL approval card armed after its gate was consumed — a
  stale card could re-submit a decision against an already-resolved gate
  ([PR #3], evidence in `docs/acceptance/22-hitl-stale-card-fix/`).
- Lifecycle scripts made bash 3.2 compatible for stock macOS.
- `log_level` and `otlp_endpoint` settings now have live consumers as
  spec §5b/§10 intend: a PATCH re-applies the log filter and repoints the
  span exporter immediately, stored values override the env bootstrap at
  startup, and never-touched settings leave the env values in charge.
- Run deletion and history purge now also remove the run's LangGraph
  checkpoint rows (orchestrator thread `run_id`, worker threads
  `run_id:*`) — previously they accumulated until `./decom.sh`.
- `docker-compose.yml` header comment updated to acknowledge the
  profile-gated `redis` service added in M7.

### Added

- Update-safe re-runs of `quick-setup.sh`: every prompt defaults to
  "keep what I have" — the provider menu pre-selects the currently keyed
  combination, existing keys are kept on Enter (answer `y` + paste to
  rotate just one), existing Redis provisioning is kept on Enter, and a
  leftover `FAKE_LLM_ENABLED=1` is only removed after asking. Plus
  `--help`/`-h` documenting the interactive walkthrough and every flag.
- Provider-choice setup: `quick-setup.sh` now asks which provider(s) to
  configure (Anthropic / Google / OpenAI, any pair, all three, or keyless
  fake mode), prompts for each selected key, and **verifies every key with
  a free list-models API call** before saving (rejected/unreachable keys
  get a save-anyway escape). Non-interactive: `--providers`,
  `--anthropic-key` / `--google-key` / `--openai-key` (legacy `--key`
  kept as an alias). All provider keys are now optional in spec §13.
- First-boot default-model resolution: if the code default's provider has
  no key when the seed pass first runs, `default_model` is stored as the
  first configured provider's flagship — `claude-sonnet-4-6` →
  `gemini-3.6-flash` → `gpt-5.6-luna` → `fake:scripted`. Explicit
  settings are never touched.
- Documentation suite ([PR #4]): architecture diagrams (C4, ERD, class,
  sequence, state machines, resolution ladder — 20 Mermaid diagrams), ten
  ADRs, API references (REST, SSE contract, workflow DSL, skill format),
  operations guides (runbook, configuration, scaling, troubleshooting,
  data lifecycle), development guides (contributing, local dev, testing,
  code tour, prompt catalog), security posture, observability guide, user
  guide, glossary, and this changelog.

### Added

- Cross-replica registry-cache invalidation over Postgres LISTEN/NOTIFY
  (channel `registry_cache_inv`, origin-tagged payloads, loop-proof;
  dormant on a single node) and optional Redis provisioning in
  `quick-setup.sh --redis` (ADR-0008).

## M8 — Answer surfaces, form gates, and provider campaigns — 2026-08-07

### Added

- Markdown-rendered canonical answers with a collapsible "show structured
  summary" toggle; the structured panel stays expanded in traces as the
  audit surface.
- HITL **form gates**: workflow gates can carry choice and text questions;
  answers are recorded verbatim on the `hitl` step and delivered into
  worker state.
- Themed pure-SVG **charts** (`bar`/`line`/`pie`) in the structured answer,
  data extracted from run content, plus a `render_chart` native tool.
- Per-skill `max_tool_iterations` loop budgets (frontmatter/registry field;
  the static `web-research` skill ships with 20).
- Current model lists for the OpenAI (GPT-5.x family) and Google
  (Gemini flash family) adapters.

### Fixed

- OpenAI reasoning-effort runs are routed through the Responses API —
  current reasoning models reject function tools + `reasoning_effort` on
  `/v1/chat/completions`; the fix lives entirely in the adapter with zero
  consumer changes (ADR-0007). Found live by the stage-19 campaign.

### Verified

- Provider agnosticism proven end to end: five conversations × both
  orchestrator modes on `openai:gpt-5.6-terra` (20/20 turns), a Gemini
  bonus run, and heterogeneous three-provider single runs (Anthropic
  orchestrator × OpenAI planner/sub-agent) — `docs/acceptance/` stages
  19–21.

## M7 — Registry cache layer and progressive-disclosure retrieval — 2026-08-07

### Added

- `RegistryCache` facade for every run-path registry/settings read, with
  live-flippable backends: `bypass` (shipped default, byte-identical direct
  reads — the rollback lever), `memory` (reload-on-dirty), and optional
  `redis`; event-driven invalidation on every write path, no TTLs
  (spec §7.3, ADR-0004). Cache status/refresh API and UI controls.
- Progressive-disclosure top-K retrieval over orchestrator catalogs: BM25 +
  embedding cosine fused with RRF, pinned ids, `use_full_catalog` escape
  hatch; off by default and active only above a per-registry threshold
  (spec §7.4, ADR-0005). Embeddings stored as JSONB via the provider port
  (ADR-0006).

### Fixed

- Settings page reflects `registry_cache_mode` flips in cache status
  immediately; typed redis imports.

## M6 — Compose stack, acceptance, and hardening — 2026-08-05 to 2026-08-06

### Added

- Three-service `docker compose up` stack with prewarmed MCP caches,
  keyless demo mode (fake-provider script control), and lifecycle scripts
  (`quick-setup.sh`, `build.sh`, `start.sh`, `stop.sh`, `decom.sh`).
- Chat experience: live activity ticker, collapsible thinking layout, stop
  button, queued follow-up message, named dispatch rails with steps grouped
  under their sub-agent rails, phonetic callsigns for ephemeral workers,
  and four brand themes (including a themed HITL gate card).
- LLM-as-judge overlap guard on skill/sub-agent saves; delete buttons for
  custom skills and sub agents; Claude Sonnet 5 / Opus 5 in the Anthropic
  adapter (Claude 5 effort maps to adaptive thinking).
- Full manual-UI acceptance evidence: the single-pass 125-screenshot
  campaign plus routing-matrix, determinism, and multi-capability retests
  (`docs/acceptance/` stages 00–17).

### Fixed

- Parallel HITL gates resolve one decision per gate with stale-interrupt-
  aware resume; interrupted tool calls replay on fresh middleware
  instances; plan entries dispatch even when the planner answers part of
  the ask directly.
- Contained tool exceptions in agentic/fallback loops; `spin_worker` strict
  UUID contract with corrective feedback; unique bound-tool names for
  duplicate registry names; schema-repair retry for
  `summarize-and-structure`.
- Reasoning content blocks render as prose (never block reprs); structlog
  renders exception tracebacks; MCP stdio subprocesses inherit network env;
  blank env values treated as unset; MCP server row refreshed after commit;
  workflow preview BFS depth capped (self-loop edge froze the tab);
  theme-correct toggles and A2UI answer cards; queued message and live-run
  view bound to their conversation.

## M5 — Admin command center — 2026-08-05

### Added

- All seven UI pages (Chat, MCP Servers, Tools, Skills, Sub Agents, Runs,
  Settings) in the mission-control design: consistent tables with
  source/kind badges, drawers, workflow DAG builder with validation,
  run trace view, A2UI answer renderer, and the Settings command center.

## M4 — Orchestrator, middleware layer, chat SSE — 2026-08-05

### Added

- Both orchestrator modes, runtime-switchable per run (ADR-0010): graph
  mode (`plan → resolve → dispatch → aggregate` with the deterministic
  capability ladder) and agentic mode (single `create_agent` concierge with
  todos, `spin_worker`, `use_full_catalog`).
- Middleware layer (spec §7.0, ADR-0003): the three registry projections,
  OOB Summarization/call-limit/TodoList middleware, all composed through
  `build_middleware_stack(context)`.
- Chat SSE event contract, HITL interrupt/resume over the Postgres
  checkpointer, run/step recording, and observability (structlog JSON,
  OTel spans, `/metrics`) with the spec §10 label set.

## M3 — Worker factory — 2026-08-05

### Added

- Record → compiled-subgraph worker factory: DAG compile with sequential,
  branch, parallel, and error edges, HITL gate compile, routing, and the
  middleware-backed skill stack.

## M2 — MCP connection manager — 2026-08-04

### Added

- MCP server connect over stdio and streamable HTTP, tool ingestion into
  the registry, `listChanged` re-ingest, health checks, and invoke coverage.

## M1 — Registries, schema, provider layer — 2026-08-04

### Added

- Postgres schema and Alembic baseline for the tri-layer registries
  (mcp_servers, tools, skills, sub_agents), registry CRUD API, static seed
  data with static-record rejection rules (immutable ids; only
  status/exposure togglable).
- The `ModelProvider` port, adapter registry, and `get_model()` single
  entry point with the shared adapter contract test suite (spec §2.1,
  ADR-0002).
- Skill documents as markdown (frontmatter + body), native `.skill.md`
  startup scan, and `{tool:...}` mention validation (ADR-0009).

[PR #1]: https://github.com/maheshyaddanapudi/concierge-agent/pull/1
[PR #2]: https://github.com/maheshyaddanapudi/concierge-agent/pull/2
[PR #3]: https://github.com/maheshyaddanapudi/concierge-agent/pull/3
[PR #4]: https://github.com/maheshyaddanapudi/concierge-agent/pull/4
