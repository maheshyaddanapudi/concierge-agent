# Configuration reference

Two layers, deliberately separate:

1. **Environment variables** — secrets and infrastructure wiring. Read once at process start (`backend/app/config.py`, `pydantic-settings`, cached via `lru_cache`). Provider API keys are **env-only by policy**: never stored in the database, never shown in the UI, never logged.
2. **Runtime settings** (`app_settings` table, `backend/app/settings_store.py`) — everything operational. Read live from the DB (through the registry cache); a `PATCH /api/v1/settings` applies to the next run with no restart.

## Environment variables

Sources: `.env.example`, `docker-compose.yml`, `backend/app/config.py`. Compose passes `${VAR:-}` for optional vars; the config module treats blank strings as unset. `quick-setup.sh` manages `ANTHROPIC_API_KEY`, `REDIS_URL`, and `COMPOSE_PROFILES` in `.env`.

| Variable | Default | Effect | Required? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | *(unset)* | Enables the `anthropic` provider adapter. Gates every `anthropic:*` model. | Yes for real use (the default model is `anthropic:claude-sonnet-4-6`); not needed in keyless demo mode |
| `GOOGLE_API_KEY` | *(unset)* | Enables the `google_genai` adapter (chat + embeddings). Presence surfaces the provider in Settings model selects. | No |
| `OPENAI_API_KEY` | *(unset)* | Enables the `openai` adapter (chat + embeddings). | No |
| `FAKE_LLM_ENABLED` | `false` | Enables the scriptable `fake` provider and mounts the `/_fake/script` control router. Combined with the `fake:scripted` model in Settings this gives a fully keyless demo stack. | No — never set it in a normally configured deployment |
| `POSTGRES_USER` | `concierge` | Compose-only: initializes the `db` container and its `pg_isready` healthcheck user. | No (defaults compiled into compose) |
| `POSTGRES_PASSWORD` | `concierge` | Compose-only: `db` container password. | No |
| `POSTGRES_DB` | `concierge` | Compose-only: database name created in the `db` container. | No |
| `DATABASE_URL` | compose: `postgresql+asyncpg://concierge:concierge@db:5432/concierge`; bare config default: `postgresql+asyncpg://postgres:postgres@localhost:5432/concierge` | Backend SQLAlchemy async engine. Also derived from for the LangGraph checkpointer (`+asyncpg` stripped → psycopg pool) and the LISTEN/NOTIFY listener connection (asyncpg). | Effectively yes outside compose defaults |
| `LANGSMITH_API_KEY` | *(unset)* | LangSmith authentication. Key only — enable/endpoint/project are runtime settings; with the key unset, `langsmith_enabled=true` silently produces no callbacks. | No |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | If set, an OTLP span exporter is attached when the tracer is first created (`backend/app/obs.py`). Unset → spans are created but not exported. | No |
| `WORKSPACE_DIR` | `/workspace` | Sandbox root for the seeded `filesystem` MCP server; compose mounts the `workspace` named volume there and hardcodes the value for the backend service. | No |
| `LOG_LEVEL` | `INFO` | structlog level, applied at process start (`configure_logging`). | No |
| `REDIS_URL` | *(unset)* | Enables the `redis` registry-cache mode (spec §7.3). URL-with-credentials stays env-only; without it, saving `registry_cache_mode=redis` is rejected with 422. `./quick-setup.sh --redis` writes `redis://redis:6379/0`. | Only for redis cache mode |
| `COMPOSE_PROFILES` | *(unset)* | Written by `quick-setup.sh` (`redis` or blank). With `redis`, `docker compose up` also starts the optional `redis:7-alpine` service (bound to `127.0.0.1:6379`). | Only for redis cache mode |
| `BACKEND_PORT` | `8000` | Host port mapped to the backend container's :8000; `start.sh` uses it for the health poll and printed URLs. | No |
| `FRONTEND_PORT` | `5173` | Host port mapped to the frontend nginx container's :80. | No |
| `VITE_API_BASE_URL` | `http://localhost:8000` | **Local dev only**: Vite dev-server proxy target (`frontend/vite.config.ts`). The production image proxies `/api/` and `/metrics` to `backend:8000` via nginx and ignores this variable. | No |

17 variables total. Anything else in the environment is ignored (`extra="ignore"` in `AppConfig`).

## Runtime settings (`app_settings`)

Defaults from `DEFAULTS` in `backend/app/settings_store.py`. Read: `GET /api/v1/settings`. Write: `PATCH /api/v1/settings` with a partial object; validation errors return 422 with the full error list. Every write invalidates the settings registry in the cache, so the next read anywhere sees the new value.

### Orchestration

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `orchestrator_mode` | `"graph"` \| `"agentic"` | `"graph"` | Mode stamped onto each new run at creation (`runner.create_run`); graph = plan→resolve→dispatch→aggregate StateGraph, agentic = single `create_agent` concierge |
| `orchestrator_full_fallback_enabled` | bool | `true` | Enables the self-service full-catalog fallback when routing fails (`graph_mode.py`) |
| `dynamic_worker_fallback_enabled` | bool | `true` | Allows rung-4 ephemeral dynamic workers in the resolution ladder (`ladder.py`) |

### Models

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `default_model` | `provider:model` string | `"anthropic:claude-sonnet-4-6"` | Fallback model for every role without an override; all model access via `get_model()` (spec §2.1) |
| `default_model_params` | object \| null (`{effort, temperature, max_output_tokens}`) | `null` | Params for the default model; validated against the model's declared support at save |
| `planner_model` | `provider:model` \| null | `null` (→ default) | Graph-mode planner structured-output call |
| `planner_model_params` | object \| null | `null` | Requires `planner_model` to be set |
| `aggregator_model` | `provider:model` \| null | `null` (→ default) | Final answer merge + answer-UI generation call |
| `aggregator_model_params` | object \| null | `null` | Requires `aggregator_model` to be set |

### Limits

| Key | Type | Default | Effect / consumer |
|---|---|---|---|
| `max_parallel_dispatch` | int ≥ 1 | `4` | Parallel dispatch cap in graph mode (`graph_mode.py`) |
| `max_plan_steps` | int ≥ 1 | `6` | Planner plan-length cap (`graph_mode.py`) |
| `max_tool_iterations` | int ≥ 1 | `8` | Global tool-loop budget, enforced via LangChain call-limit middleware (`middleware.py`); skills can carry a per-skill override (`skills.max_tool_iterations`, `factory/worker.py`) |
| `direct_exposure_cap_warning` | int ≥ 1 | `10` | UI-only threshold: Tools/Skills pages show a context-cost banner when exposures exceed it (`frontend/src/pages/ToolsPage.tsx`) |
| `mcp_health_interval_s` | int ≥ 1 | `30` | MCP ping-loop interval; read live each cycle (`mcp/manager.py`) |

### Registry cache

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `registry_cache_mode` | `"bypass"` \| `"memory"` \| `"redis"` | `"bypass"` | Storage backend of the `RegistryCache` singleton (`registry_cache.py`). `redis` requires `REDIS_URL` and a successful ping at save (else 422). Flips apply live; flipping into `memory` warm-loads |

### Retrieval (progressive disclosure, spec §7.4)

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `retrieval_enabled` | bool | `false` | Master switch for top-K catalog ranking (`retrieval.py`); off = full injection always |
| `retrieval_threshold` | int ≥ 1 | `30` | Per-registry record count above which ranking activates; below it, full injection bit-for-bit |
| `retrieval_top_k` | int ≥ 1 | `10` | Catalog truncation size when ranking is active |
| `embedding_model` | `provider:model` \| null | `null` | Embeddings for vector scoring via the provider port; validated at save; `null` = lexical-only (BM25) silently |

### Answer UI

| Key | Type | Default | Effect / consumer |
|---|---|---|---|
| `answer_ui_enabled` | bool | `true` | Post-answer A2UI generation call (`runner._maybe_answer_ui` → `answer_ui.py`); failure-safe, text answer always authoritative |
| `answer_ui_charts_enabled` | bool | `true` | Allows the `chart` component type in generated answer UI (`answer_ui.py`) |

### Observability

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `log_level` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR` | `"INFO"` | **Stored and validated, but no backend code path currently re-applies it** — logging is configured once at startup from the `LOG_LEVEL` env var (`main.py` → `configure_logging`). See "Live vs restart" below |
| `langsmith_enabled` | bool | `false` | Per-run LangSmith tracer built from settings and injected via callbacks (`obs.build_langsmith_callbacks`); needs `LANGSMITH_API_KEY` in env |
| `langsmith_endpoint` | string | `""` | LangSmith API URL; blank → `https://api.smith.langchain.com`. Self-hosted instances work by pointing this |
| `langsmith_project` | string | `"concierge-agent"` | LangSmith project name |
| `otlp_endpoint` | string | `""` | **Stored and validated, but no backend consumer** — the OTLP exporter reads the `OTEL_EXPORTER_OTLP_ENDPOINT` env var at first tracer creation (`obs.get_tracer`). See below |

### HITL

There are no `app_settings` keys for HITL. The HITL queue in Settings is a live view (`GET /api/v1/hitl/pending` — all `paused_hitl` runs), resolved per run via `POST /api/v1/runs/{id}/hitl`.

24 settings keys total.

## Live vs restart

Verified against the code, not assumed:

- **Live (22 of 24 keys)**: every key except the two below is read from the DB (through the cache, which the settings write path invalidates) at the point of use — run creation, planner call, dispatch, tool-loop construction, MCP health cycle, cache access, retrieval, answer-UI generation, LangSmith callback construction. A PATCH takes effect on the next run (or next health-loop cycle for `mcp_health_interval_s`, next model call for cache/retrieval keys) with no restart. `registry_cache_mode` even re-applies itself mid-process via the cache's own settings invalidation hook.
- **`log_level` (setting)**: validated and persisted, but `configure_logging` is only called at process start with the `LOG_LEVEL` env value. Changing the setting does not currently change the running process's log level; set the env var and restart the backend instead.
- **`otlp_endpoint` (setting)**: validated and persisted, but the span exporter is wired from the `OTEL_EXPORTER_OTLP_ENDPOINT` env var the first time a tracer is requested. Changing the setting does not currently repoint the exporter; use the env var and restart.

Spec §8.7 intends every control on the Settings page to be restart-free; for these two keys the env var is the operative knob today — treat this as a known spec/implementation gap when triaging.
