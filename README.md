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

Prerequisites: Docker + Docker Compose; an Anthropic API key (other provider keys optional — their presence enables those providers in Settings).

```bash
git clone <repo-url> && cd concierge-agent
./quick-setup.sh   # .env + API key (prompts; or --key sk-ant-...) + local deps
./build.sh         # build backend + frontend images
./start.sh         # start db/backend/frontend; schema + seeds auto-create on first run
```

Lifecycle scripts (all idempotent):

| Script | What it does |
|---|---|
| `./quick-setup.sh` | Creates `.env` from the example, prompts for `ANTHROPIC_API_KEY` (hidden input; overrides an existing value on confirm; `--key <value>` for non-interactive), asks whether to provision the optional Redis cache backend (`--redis`/`--no-redis` non-interactive; usage stays a Settings decision), installs backend (`uv sync`) and frontend (`npm install`) dev dependencies. |
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
CLAUDE.md        # spec-driven development rules for Claude Code
backend/         # FastAPI + LangGraph app (api, models, mcp, llm, native, factory, orchestrator, seed)
frontend/        # React admin: Chat, MCP Servers, Tools, Skills, Sub Agents, Runs, Settings
docker-compose.yml
```

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

**Registry cache (spec §7.3)** — every registry/settings read in the run path goes through one `RegistryCache` facade (`backend/app/registry_cache.py`); the `registry_cache_mode` setting flips its backend live between `bypass` (direct DB reads — the shipped default and rollback lever), `memory` (in-process, event-invalidated on every write path, manual refresh buttons on the Tools/Skills/Sub Agents pages and in Settings), and `redis` (optional: `docker compose --profile redis up` + `REDIS_URL`). **Retrieval (spec §7.4)** — off by default; when enabled, orchestrator catalogs above the threshold are ranked to the task's top-K (BM25 + optional embeddings via the provider port, RRF-fused) with pinned ids and an explicit `use_full_catalog` footer; skill loops and workers remain id-pinned contracts, never ranked.

## Development

Spec-driven: read `CLAUDE.md` first. Tests: `cd backend && pytest` · lint: `ruff check . && mypy app` · frontend: `npm run lint && npm run test`. LLM calls in tests run against a fake chat model through the provider port (`fake:scripted`, enabled by `FAKE_LLM_ENABLED=1` which the test suite sets itself) — no keys needed for the suite.

Backend dev setup: `cd backend && uv sync` (Python 3.12). The pytest suite needs a Postgres it can own: `docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:16`, create a `concierge_test` database, or point `TEST_DATABASE_URL` at your own instance. Schema is managed by Alembic (`alembic upgrade head`, run automatically at app startup).

## Scope notes

This is a POC: authentication/authorization, multi-tenancy, and production hardening are deliberately out of scope. Provider and LangSmith API keys are env-only — never stored in the database or shown in the UI. Post-POC roadmap (spreadsheet-driven evals at skill and sub agent level, published to LangSmith) is designed-for in spec.md §15.
