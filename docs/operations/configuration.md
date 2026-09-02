# Configuration reference

Two layers, deliberately separate:

1. **Environment variables** — secrets and infrastructure wiring. Read once at process start (`backend/app/config.py`, `pydantic-settings`, cached via `lru_cache`). Provider API keys are **env-only by policy**: never stored in the database, never shown in the UI, never logged.
2. **Runtime settings** (`app_settings` table, `backend/app/settings_store.py`) — everything operational. Read live from the DB (through the registry cache); a `PATCH /api/v1/settings` applies to the next run with no restart.

## Environment variables

Sources: `.env.example`, `docker-compose.yml`, `backend/app/config.py`. Compose passes `${VAR:-}` for optional vars; the config module treats blank strings as unset. `quick-setup.sh` manages the three provider keys (chosen via its provider menu, each verified with a free list-models call before saving), `FAKE_LLM_ENABLED`, `REDIS_URL`, and `COMPOSE_PROFILES` in `.env`.

| Variable | Default | Effect | Required? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | *(unset)* | Enables the `anthropic` provider adapter. Gates every `anthropic:*` model. | No — any one provider key (or fake mode) suffices. If unset at first boot, the seed pass resolves `default_model` to the first configured provider's flagship (`gemini-3.6-flash` → `gpt-5.6-luna` → `fake:scripted`); an explicitly saved setting is never touched |
| `GOOGLE_API_KEY` | *(unset)* | Enables the `google_genai` adapter (chat + embeddings). Presence surfaces the provider in Settings model selects. | No |
| `OPENAI_API_KEY` | *(unset)* | Enables the `openai` adapter (chat + embeddings). | No |
| `FAKE_LLM_ENABLED` | `false` | Enables the scriptable `fake` provider and mounts the `/_fake/script` control router. Combined with the `fake:scripted` model in Settings this gives a fully keyless demo stack. | No — never set it in a normally configured deployment |
| `POSTGRES_USER` | `concierge` | Compose-only: initializes the `db` container and its `pg_isready` healthcheck user. | No (defaults compiled into compose) |
| `POSTGRES_PASSWORD` | `concierge` | Compose-only: `db` container password. | No |
| `POSTGRES_DB` | `concierge` | Compose-only: database name created in the `db` container. | No |
| `DATABASE_URL` | compose: `postgresql+asyncpg://concierge:concierge@db:5432/concierge`; bare config default: `postgresql+asyncpg://postgres:postgres@localhost:5432/concierge` | Backend SQLAlchemy async engine. Also derived from for the LangGraph checkpointer (`+asyncpg` stripped → psycopg pool) and the LISTEN/NOTIFY listener connection (asyncpg). | Effectively yes outside compose defaults |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | `5` / `10` / `30` | M50: the per-replica SQLAlchemy pool budget — pooled ceiling is `DB_POOL_SIZE + DB_MAX_OVERFLOW` connections; `DB_POOL_TIMEOUT` is the seconds a request waits for one before failing. The LangGraph checkpointer pool (10), the LISTEN connection and the ambient leader lease sit outside it: size Postgres `max_connections` from `replicas × (pool + overflow + 12)` with headroom. Streams (`/chat/stream`, `/ambient/stream`) hold no pooled connection. | Restart |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | `120` / `2` | M51: the per-call timeout and retry budget applied to **every** provider adapter at the port (`port_limits()` in `app/llm/adapters.py`) — the one place a hang or a retry storm is bounded. A provider failure reaches the run as a classified error (rate-limited / timeout / unknown or retired model / provider error) naming the model and the setting that resolved it; `concierge_llm_errors_total{kind}` counts them. | Restart |
| `SHUTDOWN_GRACE_S` | `25` | M51: on SIGTERM the process flips `GET /ready` to 503, refuses new runs (503 + `Retry-After`), waits this long for in-flight runs to finish, then cancels the remainder — each ends `cancelled` with an error naming the shutdown and the grace. The next boot reaps anything still `running`/`queued` as "orphaned by a restart". M53: uvicorn closes the listening socket at SIGTERM *before* the lifespan drain runs and waits up to `--timeout-graceful-shutdown 5` for open connections (sse-starlette ends open streams at once), so the sequence is 5 s + this grace, under the compose `stop_grace_period` of 40 s (Kubernetes: `terminationGracePeriodSeconds`). To let a balancer see the 503 *before* the port closes, send **`SIGUSR1`** first — the pre-stop hook `deploy.sh` uses: readiness flips, new runs are refused, streams the process cannot serve are closed with a reconnect hint, runs executing here keep streaming to their end. | Restart |
| `EGRESS_POLICY` / `EGRESS_ALLOW_HOSTS` / `EGRESS_MAX_BYTES` | `public` / *(empty)* / `5242880` | M52: one policy for every outbound fetch the platform makes on someone else's say-so — A2A card fetches and calls, `http_json`/`rss` poll sources, HTTP MCP servers, the webhook channel. `public` refuses loopback, link-local (cloud metadata), private, reserved, multicast and unspecified targets, both by literal address and by what the hostname resolves to — except the hosts you name in `EGRESS_ALLOW_HOSTS` (hosts or `.suffixes`), which are admitted whatever they resolve to: that is how an internal MCP server or agent is named without opening the policy; `allowlist` admits only those hosts; `open` keeps only the caps. Every redirect hop is re-checked (at most five); bodies stream and are cut past `EGRESS_MAX_BYTES`; a refusal has one shape, `egress refused: <kind>`, and `concierge_egress_refused_total{kind}` counts it. Save-time checks at the API are static (scheme, literal address, allowlist); the resolved-address check runs at connect/fetch time. Only http(s) ever passes. | Restart |
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
| `dynamic_worker_fallback_enabled` | bool | `true` | Allows rung-4 ephemeral dynamic workers in the resolution ladder (`ladder.py`). They compose `direct_exposure=true` skills only, whatever this is set to |

### Models

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `default_model` | `provider:model` string | `"anthropic:claude-sonnet-4-6"` | Fallback model for every role without an override; all model access via `get_model()` (spec §2.1) |
| `default_model_params` | object \| null (`{effort, temperature, max_output_tokens}`) | `null` | Params for the default model; validated against the model's declared support at save |
| `planner_model` | `provider:model` \| null | `null` (→ default) | Graph-mode planner structured-output call |
| `planner_model_params` | object \| null | `null` | Requires `planner_model` to be set |
| `aggregator_model` | `provider:model` \| null | `null` (→ default) | Final answer merge (graph mode); the formatter has its own model key |
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
| `formatter_enabled` | bool | `true` | The formatter role (spec §7.1): off = the post-answer transform call never runs and no structured artifact exists — raw renders directly (`runner._maybe_format_answer` → `answer_ui.py`) |
| `formatter_presentation` | `a2ui_first`\|`raw_first` | `"a2ui_first"` | Which view is primary; frozen onto each run's artifact — history renders by run-time facts |
| `formatter_model` | string\|null | `null` | Formatter's model; null → `default_model` (single hop, like planner/aggregator) |
| `formatter_model_params` | object\|null | `null` | Effort/params for the formatter call |
| `formatter_coverage_flag_threshold` | int 1–100 | `90` | Amber coverage flag below this — visual only, never a render gate |
| `answer_ui_charts_enabled` | bool | `true` | Allows the `chart` component type in generated answer UI (`answer_ui.py`) |

### Observability

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `log_level` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR` | `"INFO"` | Applies live: a PATCH re-runs `configure_logging` immediately (`settings_store.update_settings`), and a stored value overrides the `LOG_LEVEL` env bootstrap at startup |
| `langsmith_enabled` | bool | `false` | Per-run LangSmith tracer built from settings and injected via callbacks (`obs.build_langsmith_callbacks`); needs `LANGSMITH_API_KEY` in env |
| `langsmith_endpoint` | string | `""` | LangSmith API URL; blank → `https://api.smith.langchain.com`. Self-hosted instances work by pointing this |
| `langsmith_project` | string | `"concierge-agent"` | LangSmith project name |
| `otlp_endpoint` | string | `""` | Applies live: a PATCH repoints the span exporter (`obs.apply_otlp_endpoint`); empty disables export. Overrides the `OTEL_EXPORTER_OTLP_ENDPOINT` env bootstrap; a stored value is re-applied at startup |

### HITL

There are no `app_settings` keys for HITL. The HITL queue in Settings is a live view (`GET /api/v1/hitl/pending` — all `paused_hitl` runs), resolved per run via `POST /api/v1/runs/{id}/hitl`.

28 settings keys total.

### Retention, cost and MCP reconnection (M53)

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `retention_<table>_enabled` for `ambient_events`, `deliveries`, `ambient_policies`, `pattern_instances`, `a2a_tasks`, `auth_sessions` | boolean | `false` for five, `true` for `auth_sessions` | the gate of that table's purge, enforced inside the purge (`app/retention.py`) — off means nothing is deleted, whoever calls it. Deleting is irreversible, so every gate but the expired-session sweep is born off (the login path already swept expired sessions) |
| `retention_<table>_days` | integer 1–3650 | 30 / 90 / 365 / 7 / 90 / 7 | the window: only rows the system is finished with AND older than this are eligible — processed events, delivered or superseded deliveries, superseded policy rows (never the newest per category), matched/expired pattern instances, terminal A2A tasks, sessions past expiry. `GET /retention` previews the eligible counts; `POST /retention/run` runs now; the periodic loop runs hourly under an advisory lock |
| `mcp_auto_reconnect_enabled` | boolean | `true` | a server that fails to connect or fails a health ping is retried with backoff (5 s doubling to 5 min). Off: it stays `error` until reconnected by hand |
| `mcp_reconnect_max_attempts` | integer 1–100 | `8` | consecutive failures before the circuit opens; the row's `last_error` says so and the reconnect button resets it |
| `model_prices` | object `{"provider:model": {"input_per_m", "output_per_m"}}` | `{}` | USD per million tokens; an override wins over a provider-reported price (OpenRouter publishes one per model, refreshed hourly) and the built-in reference table (`app/llm/pricing.py`). A model none of them know is unpriced — reported, never guessed |
| `spend_ceiling_enabled` | boolean | `false` | the gate of the shared spend ceiling; off is the pre-M53 admission, byte-identical |
| `spend_ceiling_usd_per_day` | number > 0 | `10.0` | one ceiling across every run kind (chat, direct, ambient, eval), summed from the database over the UTC day so every replica sees the same number. Past it: chat 429 + `Retry-After`, ambient fire held on its event with the reason, eval batch stops. `GET /spend` reports the day |

## Live vs restart

Verified against the code, not assumed:

- **Live (all 24 keys)**: every key is read from the DB (through the cache, which the settings write path invalidates) at the point of use — run creation, planner call, dispatch, tool-loop construction, MCP health cycle, cache access, retrieval, answer-UI generation, LangSmith callback construction. A PATCH takes effect on the next run (or next health-loop cycle for `mcp_health_interval_s`, next model call for cache/retrieval keys) with no restart. `registry_cache_mode` re-applies itself mid-process via the cache's own settings invalidation hook.
- **`log_level` and `otlp_endpoint`** apply even faster than "next run": the settings write path calls their consumers directly (`configure_logging` / `apply_otlp_endpoint` in `settings_store.update_settings`), so they take effect the moment the PATCH returns. The env vars (`LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`) are bootstrap defaults only; an explicitly stored setting is re-applied over them at startup, and a never-touched setting leaves the env value in charge.
