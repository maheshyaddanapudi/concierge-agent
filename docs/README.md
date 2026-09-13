# Documentation

Complete documentation for the Concierge Agent POC. `spec.md` at the repo root remains the **specification** (what the system must do); these documents describe **what was built and how to work with it**. All diagrams are Mermaid — they render directly on GitHub and diff in pull requests.

## Architecture

| Document | Contents |
|---|---|
| [architecture/overview.md](./architecture/overview.md) | The system in 10 minutes; C4 context, container, and component diagrams; deployment topology; end-to-end data flow; index of key design decisions |
| [architecture/data-model.md](./architecture/data-model.md) | The 37 application tables by domain, an ERD of the registry + run core, per-table semantics, static-vs-dynamic rules, the typed embedding columns, checkpoint storage, schema-change workflow |
| [architecture/components.md](./architecture/components.md) | Class diagrams of the load-bearing internals: provider port and adapters, registry cache, middleware stack, worker factory, retrieval pipeline |
| [architecture/runtime-flows.md](./architecture/runtime-flows.md) | Sequence diagrams: graph-mode run, agentic-mode run, HITL pause/resume, MCP server plug-in, cache invalidation and cross-replica sync |
| [architecture/state-machines.md](./architecture/state-machines.md) | Run status lifecycle, MCP server states, the frontend HITL gate lifecycle |
| [architecture/resolution-ladder.md](./architecture/resolution-ladder.md) | Flowchart and rung-by-rung walkthrough of capability resolution, including the retrieval gate and full-catalog fallback |

## Decisions

| Document | Contents |
|---|---|
| [adr/](./adr/README.md) | Ten Architecture Decision Records covering the M1–M8 core: no broker (0001), provider port (0002), middleware precedence (0003), the registry-cache facade (0004 — its *default* was later amended to `memory`; the record says so), hybrid retrieval (0005), JSONB-before-pgvector (0006), OpenAI Responses API routing (0007), LISTEN/NOTIFY sync (0008), skills as markdown (0009), two orchestrator modes (0010). The M13–M56 decisions (the auth seam, the control plane, the fence and egress policy, the job-clock split) are recorded in `spec.md` and the CHANGELOG, not as ADRs — see the note in [adr/README.md](./adr/README.md) |
| [../CHANGELOG.md](../CHANGELOG.md) | Project history, milestone by milestone (M1–M56) plus the post-release campaign, schema-drift, hardening-wave and third-reading entries |

## API & interfaces

| Document | Contents |
|---|---|
| [api/rest-api.md](./api/rest-api.md) | Conventions (error envelope, status-code semantics) and the endpoint reference for all 86 paths / 115 operations under `/api/v1`, router by router |
| [api/sse-events.md](./api/sse-events.md) | The chat/run event-stream contract: every event type, payload schemas, replay and ordering guarantees, client guidance |
| [api/workflow-dsl.md](./api/workflow-dsl.md) | Sub-agent workflow JSON reference: node types, edge rules, HITL form-gate questions, validation catalog, worked example |
| [api/skill-format.md](./api/skill-format.md) | The `.skill.md` authoring reference: frontmatter schema, binding rules, annotated example |

## Operations

| Document | Contents |
|---|---|
| [operations/runbook.md](./operations/runbook.md) | Day-2 procedures: lifecycle scripts, health checks, mode/model/cache flips, MCP recovery, HITL triage, incident quick reference |
| [operations/configuration.md](./operations/configuration.md) | Every environment variable and every runtime Settings key, with defaults, effects, and consumers |
| [operations/scaling.md](./operations/scaling.md) | The scale-out path: multi-replica realities (SSE stickiness, LISTEN/NOTIFY), memory→redis promotion, JSONB→pgvector swap |
| [operations/troubleshooting.md](./operations/troubleshooting.md) | Symptom-indexed fixes: provider errors, MCP issues, cache staleness, SSE drops, 409 semantics, and more |
| [operations/data-lifecycle.md](./operations/data-lifecycle.md) | Volumes, stop-vs-decom, seeds, run-data growth and purge, retention for the nine gated tables (the six M53 ambient/auth ledgers plus the run ledger), checkpoints, backup guidance |
| [operations/backup-restore.md](./operations/backup-restore.md) | The backup/restore drill (M53): `backup.sh` / `restore.sh`, what a dump does not contain, the measured RTO |
| [operations/runbooks/](./operations/runbooks/README.md) | One page per failure class: pool exhaustion, wedged tick, leader loss, provider outage, delivery backlog, dead replica, spend ceiling, MCP circuit open, LISTEN down, checkpointer outage, Redis outage, embedding backfill stuck, stalled run — the metric that reveals it, the action that resolves it |

## Development

| Document | Contents |
|---|---|
| [extending.md](./extending.md) | The fork seam (spec §20): the `AuthProvider` port a fork implements in one module, what the core guarantees and will never do, how to wire and test it, the reference stub |
| [development/contributing.md](./development/contributing.md) | The spec-driven workflow, conventional commits, hard constraints reviews enforce, PR evidence expectations |
| [development/local-development.md](./development/local-development.md) | Both dev loops: full containerized stack and the fast uv/vite loop; keyless fake-LLM mode |
| [development/testing.md](./development/testing.md) | Test suite map (62 backend modules, 14 frontend suites), the fake-provider philosophy, dual-cache-mode gate, how-to-add checklists |
| [development/code-tour.md](./development/code-tour.md) | Guided tour of every backend top-level module and package and every frontend page, plus a "where would I change X?" table |
| [development/prompts.md](./development/prompts.md) | The prompt loader, the golden-set regression harness and the fence-token rule, with the orchestration prompts described in prose; `backend/app/prompts/golden/` is the authoritative per-prompt index (27 prompt files today) |

## Cross-cutting

| Document | Contents |
|---|---|
| [security.md](./security.md) | Honest POC security posture: non-goals, secrets handling, trust boundaries, prompt-injection exposure, hardening checklist |
| [observability.md](./observability.md) | Traces, the shared label set, structured logging, Prometheus metrics incl. the M53 incident signals, OTel and LangSmith switches, token usage |
| [observability/](./observability/README.md) | Prometheus + Grafana provisioning and the two dashboards (saturation, LLM) — operator tooling, not a shipped service |
| [user-guide.md](./user-guide.md) | Operator walkthrough of all eleven UI pages (two of them gated on a master switch), task by task |
| [glossary.md](./glossary.md) | The decoder ring: 52 project terms, each grep-verified against the codebase |

## Evidence

| Document | Contents |
|---|---|
| [acceptance/](./acceptance/README.md) | The acceptance record driven by the checked-in Playwright/shell drivers: stages 00–36 (316 frames) plus the M34 and M49–M56 production drills and the post-release fix, drift, hardening-wave and third-reading runs under `prod/` (20 frames), with a transcript per stage and drill |
