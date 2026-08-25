# Concierge Agent

A registry-driven, tri-layer agentic orchestration POC: **Tools → Skills → Sub Agents**, every tier backed by a Postgres registry with static (seeded) and dynamic (admin-UI) entries, projected live into running agents through middleware, and fronted by a full admin command center.

**Goal**: plug an MCP server from the UI after startup, compose a skill from its tools, compose a sub agent from skills with a branching DAG workflow, and invoke it through chat with a visible run trace — without restarting the app. The complete definition of done is the 11-step acceptance script in [spec.md §14](./spec.md).

> **Status: all six milestones complete.** Backend + admin UI live, all test suites green, and the 11-step acceptance script (spec.md §14) executed top to bottom against a fresh `docker compose up`. Full manual-UI acceptance evidence — a single-pass, 125-screenshot campaign on genuine Claude Sonnet 5, covering both orchestrator modes × thinking on/off, all four themes, HITL approve/deny/queue, failure/retry, and every admin surface — lives in [docs/acceptance/](./docs/acceptance/README.md). `spec.md` is the single source of truth; implementation proceeded milestone by milestone via spec-driven development (see `CLAUDE.md`).

## Architecture at a glance

```
                        ┌─────────────────────────────┐
        Chat / SSE ───► │  Orchestrator (2 modes)     │
                        │  graph: plan→resolve→       │
                        │         dispatch→aggregate  │
                        │  agentic: create_agent +    │
                        │           middleware stack  │
                        └──────────┬──────────────────┘
                     resolution ladder: direct → native
                     → custom → ephemeral worker
                     (+ full-catalog fallback)
                        ┌──────────▼──────────────────┐
                        │  Sub Agents (native|custom) │  DAG: branch/parallel/
                        │  Skills (native|custom)     │  error edges/HITL
                        │  Tools  (mcp|native)        │  skills = markdown docs
                        └──────────┬──────────────────┘
                        ┌──────────▼──────────────────┐
                        │  Postgres registries        │  single source of truth
                        │  (+ runs, settings,         │  middleware = live
                        │   checkpoints)              │  projection per model call
                        └─────────────────────────────┘
```

Key design decisions (full detail in spec.md):

- **Registries, not a bus**: three Postgres-backed registries are passive shared state; execution is direct in-process calls. No broker, no queue, no Redis.
- **Middleware sync backbone**: custom Tools/Skills/SubAgents registry middlewares project registry state into every `create_agent` loop, fresh per model call — a newly plugged MCP tool is callable on the next loop iteration. Out-of-box middleware (TodoList, Summarization, call limits) everywhere else.
- **Two orchestrator modes**, runtime-switchable per run: `graph` (hand-built StateGraph with explicit planner, deterministic resolution ladder, parallel dispatch) and `agentic` (single `create_agent` concierge with todo-driven planning). Same registries, same traces — built to be A/B compared.
- **Skills are markdown documents** (frontmatter + multi-step instructions body): native ones as `.skill.md` files, custom ones authored in the UI from a template. Tool binding = strict availability; a skill's loop sees only its bound tools, ever.
- **Sub agent workflows are validated DAGs** (branching, parallel fan-out/join, error edges, human-in-the-loop pause/approve) compiled by a worker factory into LangGraph subgraphs; `create_agent` at the leaves, StateGraph as the shell.
- **Provider-agnostic by port**: a `ModelProvider` protocol + adapter registry; Anthropic, Gemini, OpenAI as thin built-in adapters; every model reference is a `provider:model` string. A custom gateway adapter drops in with zero consumer changes.
- **Everything traced**: always-on Postgres run traces, optional OpenTelemetry, optional LangSmith (local or remote by endpoint, hot-switchable), one shared label set (`tier/kind/source/run_id/...`).
- **Overlap guard**: saving a skill or sub agent first runs an LLM-as-judge duplicate check against the live registries (skills vs skills+tools, sub agents vs sub agents+skills); at ≥70% overlap the UI asks to confirm or cancel in favor of the existing match. Advisory and fail-open — never blocks a save on judge trouble; tools are exempt (dynamic MCP ingest).
- **Command center**: every runtime control lives in the admin UI — registries with cross-reference badges, MCP lifecycle, exposure toggles, orchestrator mode, models, limits, HITL queue, run cancel/retry, observability switches. No restarts.

## Stack

Python 3.12 · FastAPI · LangGraph · LangChain (`create_agent`, middleware, MCP adapters) · SQLAlchemy 2 + Alembic · Postgres 16 · React 19 + Vite + TypeScript + Tailwind · react-flow · docker-compose (`db`, `backend`, `frontend`).

## Getting started

**[QUICK_START.md](./QUICK_START.md)** walks the whole lifecycle — setup, build, start, stop, decommission, optional Redis, common issues. The short version:

Prerequisites: Docker + Docker Compose; an API key for at least one provider — Anthropic, Google, or OpenAI, any combination (only keyed providers appear in the UI's model selects; keyless demo mode also works — see QUICK_START).

```bash
git clone <repo-url> && cd concierge-agent
./quick-setup.sh   # .env + provider choice + verified API keys + local deps
./build.sh         # build backend + frontend images
./start.sh         # start db/backend/frontend; schema + seeds auto-create on first run
```

Lifecycle scripts (all idempotent):

| Script | What it does |
|---|---|
| `./quick-setup.sh` | Creates `.env` from the example, asks which provider(s) to configure (Anthropic / Google / OpenAI, any pair, all three, or keyless fake mode), prompts for each selected key (hidden input) and **verifies it with a free list-models call** before saving (with a save-anyway escape), asks whether to provision the optional Redis cache backend (usage stays a Settings decision), installs backend (`uv sync`) and frontend (`npm install`) dev dependencies. Non-interactive: `--providers a,b`, `--anthropic-key`/`--google-key`/`--openai-key`, `--redis`/`--no-redis`. First boot resolves `default_model` from whichever providers are keyed. |
| `./build.sh` | Builds both docker images. |
| `./start.sh` | Errors out if Docker isn't running; otherwise creates or restarts the stack — missing images are pulled/built, first run creates the DB schema and loads seeds automatically, later runs resume with the same data (named volumes). Waits for backend health and prints the URLs. |
| `./stop.sh` | Stops the containers; all data preserved — `./start.sh` resumes where you left off. |
| `./decom.sh` | Dismantles everything (containers, network, **data volumes** — asks for confirmation, `-y` to skip). The next `./start.sh` is a clean slate: fresh schema, seeds reloaded. Images are kept; rebuild with `./build.sh` after code changes. |

Equivalent manual path: `cp .env.example .env && docker compose up`.

Frontend at `http://localhost:${FRONTEND_PORT}`, API at `http://localhost:${BACKEND_PORT}`. Seed data loads on first start: two stdio MCP servers (fetch, filesystem), two native skills, one native tool, and the `research-concierge` sub agent. Walk spec.md §14 to exercise everything.

**Keyless demo mode**: with no provider keys, set `FAKE_LLM_ENABLED=1` in `.env` and pick `fake:scripted` as the default model in Settings — the whole stack (runs, SSE, HITL, both orchestrator modes) works against the scriptable fake provider from spec §11. A `/_fake/script` control endpoint (only mounted when the flag is set) lets you script exact model behavior, which is how the acceptance walk drives deterministic runs.

## Repository layout

```
spec.md          # the specification — single source of truth
QUICK_START.md   # setup → build → start → stop → decom, script by script
CLAUDE.md        # spec-driven development rules for Claude Code
CHANGELOG.md     # project history, milestone by milestone
backend/         # FastAPI + LangGraph app (api, models, mcp, llm, native, factory, orchestrator, seed)
frontend/        # React admin: Chat, MCP Servers, Tools, Skills, Sub Agents, Runs, Settings
docs/            # full documentation suite (see below)
docker-compose.yml
```

## Documentation

The **[docs/ index](./docs/README.md)** covers the whole suite. Highlights:

- **[Architecture](./docs/architecture/overview.md)** — C4 context/container/component diagrams, [ERD](./docs/architecture/data-model.md), [class diagrams](./docs/architecture/components.md), [sequence diagrams](./docs/architecture/runtime-flows.md) for both orchestrator modes + HITL + MCP + cache sync, [state machines](./docs/architecture/state-machines.md), and the [resolution ladder](./docs/architecture/resolution-ladder.md). All Mermaid, all rendered by GitHub.
- **[ADRs](./docs/adr/README.md)** — ten decision records covering every load-bearing choice.
- **[API reference](./docs/api/rest-api.md)** — REST conventions and endpoints, the [SSE event contract](./docs/api/sse-events.md), the [workflow DSL](./docs/api/workflow-dsl.md), and the [skill document format](./docs/api/skill-format.md).
- **[Operations](./docs/operations/runbook.md)** — runbook, [configuration reference](./docs/operations/configuration.md) (every env var and settings key), [scaling path](./docs/operations/scaling.md), [troubleshooting](./docs/operations/troubleshooting.md), [data lifecycle](./docs/operations/data-lifecycle.md).
- **[Development](./docs/development/contributing.md)** — contributing, [local dev loops](./docs/development/local-development.md), [testing strategy](./docs/development/testing.md), [code tour](./docs/development/code-tour.md), [prompt catalog](./docs/development/prompts.md).
- **[Security](./docs/security.md)** · **[Observability](./docs/observability.md)** · **[User guide](./docs/user-guide.md)** · **[Glossary](./docs/glossary.md)**
- **[Acceptance evidence](./docs/acceptance/README.md)** — stages 00–22, 130+ real-model UI screenshots.

## Milestone status

| # | Deliverable | Status |
|---|---|---|
| M1 | Postgres schema + registry API + seed + static rejection rules | ✅ complete |
| M2 | MCP manager: stdio + http connect, ingest, listChanged, health | ✅ complete |
| M3 | Worker factory + validation (branch, parallel, error edges, HITL compile) | ✅ complete |
| M4 | Orchestrator both modes + middleware layer + chat SSE + HITL + observability | ✅ complete |
| M5 | Admin UI: all seven pages incl. Settings command center | ✅ complete |
| M6 | Test suites green + compose polish + acceptance script passes | ✅ complete |
| M7 | Registry cache layer (spec §7.3: bypass/memory/redis, event invalidation, refresh UI) + progressive-disclosure retrieval (spec §7.4: hybrid top-K, embeddings port — dark by default) | ✅ complete |
| M10 | Direct sub-agent invocation (spec §7.5: `direct_exposure` gate, `POST /sub-agents/{id}/invoke`, chat target picker, `orchestrator_mode='direct'` runs with full lifecycle — HITL, formatter, trace parity) | ✅ complete |
| M11 | Opt-in history summary for direct invocations (spec §7.5: `include_history_summary` flag, one traced summarization call, composer checkbox with strict visibility rules, `+ctx` markers — cold by default, byte-identical without the flag) | ✅ complete |
| M12 | Declarative `.agent.md` static sub-agents (spec §3.4: frontmatter + §3.5 workflow with skill-by-name resolution, seed-time factory validation, error/inactive lifecycle, toggle-preserving reseeds — seeded `workspace-reporter` example) | ✅ complete |
| M13 | Memory substrate (spec §16.1: pgvector store, bi-temporal supersession, admission gate, hybrid recall, settings — dark by default) | ✅ complete |
| M14 | Episodic layer (spec §16.3: run digests, conversation rollups, prompt-assembly injection with budgets + data-fencing) | ✅ complete |
| M15 | Semantic layer (spec §16.4: extraction pipeline, LLM-match/code-resolve reconciliation, instruction quarantine, memory tools + Memory UI) | ✅ complete |
| M16 | Procedural layer (spec §16.5: plan exemplars with vote lifecycle, routing stats, fallback mining → inactive skill proposals) | ✅ complete |
| M17 | Consolidation (spec §16.6: decay sweep, generative reflection with evidence citations, contradiction sweep, advisory-locked jobs) + experiment harness | ✅ complete |
| M18 | Closed-loop refinement (spec §16.7: citation feedback — only cited memories reinforce; digest compaction — episodic store stays O(conversations); entity-hop recall; 90-day time-warp simulation) | ✅ complete |
| M19 | OpenRouter gateway adapter (spec §2.1 custom-gateway scenario) + six-model cross-provider retest matrix | ✅ complete |
| M20 | Ambient substrate (spec §17.1/17.2: event store with cascade guards, routines + hashed fire tokens, NOTIFY-wake drain, presence + real idle detector — dark by default) | ✅ complete |

**Direct sub-agent invocation (spec §7.5)** — a sub agent with `direct_exposure=true` (toggle on its detail drawer; static seeds ship exposed) can be invoked without the planner: pin it in the chat composer's target picker (or the "Invoke →" row action on the Sub Agents page), or call `POST /api/v1/sub-agents/{id}/invoke` with `{message}`. The pin replaces only the routing decision — direct runs keep the shared lifecycle: SSE streaming, HITL pause/resume, run/step trace with a pinned `route` step, metrics under `mode='direct'`, and the formatter treatment (on = structured `answer_ui`, off = raw markdown) identical to routed runs.

**Declarative agent files (spec §3.4)** — a static custom sub agent is now just a markdown file: drop `name.agent.md` (frontmatter: name/description/persona/model/direct_exposure + the §3.5 workflow, skill nodes referencing skills **by name**) into `backend/app/native/sub_agents/` and the seed scan resolves names to registry uuids, runs the same structural + factory-compile validation the API applies at save, and upserts it (`source='static'`, provenance in `native_ref`). Invalid files land as `status='error'` in the UI instead of crashing boot; removing a file deactivates its row; user status/exposure toggles survive reseeds. The seeded `workspace-reporter` (audit → form-gate approval → report write) is the living example.

**Seeded native tier (spec §9)** — the seed now exercises every registry tier natively: two native skills built from previously-untagged filesystem tools (`workspace-auditor`: read-only tree/sizes/search/metadata; `workspace-curator`: create/move/read-batch, tidy-never-delete) and `workspace-warden`, the first seeded **native sub agent** — a hand-written two-stage LangGraph (`audit → curate`) over both skills, registered via `@native_sub_agent` with covered skills resolved from names to registry uuids at seed time. It ships exposed, so the native tier answers to all four direct-invocation surfaces out of the box.

**Memory layers (spec §16)** — an opt-in, CoALA-shaped memory subsystem behind one master switch (`memory_enabled`, default **off** — the run path is byte-identical when dark). L1 episodic: every completed run gets a round-level digest and its conversation a rolling rollup, recalled cross-conversation at prompt assembly. L2 semantic: an extraction pass distills durable facts/preferences/entities through a deterministic admission gate (confidence, length, near-dup cosine), reconciles against neighbors (LLM answers only same/related/unrelated; code decides supersession by event time), and quarantines anything instruction-shaped until a human approves it on the Memory page. L3 procedural: successful plans become few-shot exemplars with a reuse-vote lifecycle, and repeated full-catalog fallbacks are mined into inactive skill proposals. L4 consolidation: Ebbinghaus-style decay, evidence-cited reflection, and a contradiction sweep run as advisory-locked periodic jobs. Storage is bi-temporal (facts are superseded, never overwritten — "what did we believe on date X" stays answerable), recall is hybrid (Postgres FTS + pgvector, RRF-fused with recency/importance), and injected blocks are data-fenced with per-section budgets. Live layer-ablation results: `experiments/memory/` + `docs/research/memory/07-experiment-results.md`.

**Registry cache (spec §7.3)** — every registry/settings read in the run path goes through one `RegistryCache` facade (`backend/app/registry_cache.py`); the `registry_cache_mode` setting flips its backend live between `bypass` (direct DB reads — the shipped default and rollback lever), `memory` (in-process, event-invalidated on every write path, manual refresh buttons on the Tools/Skills/Sub Agents pages and in Settings), and `redis` (optional: `docker compose --profile redis up` + `REDIS_URL`). **Retrieval (spec §7.4)** — off by default; when enabled, orchestrator catalogs above the threshold are ranked to the task's top-K (BM25 + optional embeddings via the provider port, RRF-fused) with pinned ids and an explicit `use_full_catalog` footer; skill loops and workers remain id-pinned contracts, never ranked.

## Development

Spec-driven: read `CLAUDE.md` first. Tests: `cd backend && pytest` · lint: `ruff check . && mypy app` · **seed documents**: `python -m app.doclint` (validates every `.skill.md` / `.agent.md` offline — the same checks the seed applies, wired as a Docker build gate and a pytest regression gate, so a malformed document fails the build rather than surfacing as a missing skill or a `status='error'` agent at boot) · frontend: `npm run lint && npm run test`. LLM calls in tests run against a fake chat model through the provider port (`fake:scripted`, enabled by `FAKE_LLM_ENABLED=1` which the test suite sets itself) — no keys needed for the suite.

Backend dev setup: `cd backend && uv sync` (Python 3.12). The pytest suite needs a Postgres it can own: `docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:16`, create a `concierge_test` database, or point `TEST_DATABASE_URL` at your own instance. Schema is managed by Alembic (`alembic upgrade head`, run automatically at app startup).

## Scope notes

This is a POC: authentication/authorization, multi-tenancy, and production hardening are deliberately out of scope. Provider and LangSmith API keys are env-only — never stored in the database or shown in the UI. Post-POC roadmap (spreadsheet-driven evals at skill and sub agent level, published to LangSmith) is designed-for in spec.md §15.
