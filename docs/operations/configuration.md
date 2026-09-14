# Configuration reference

Two layers, deliberately separate:

1. **Environment variables** — secrets and infrastructure wiring. Read once at process start (`backend/app/config.py`, `pydantic-settings`, cached via `lru_cache`). Provider API keys are **env-only by policy**: never stored in the database, never shown in the UI, never logged.
2. **Runtime settings** (`app_settings` table, `backend/app/settings_store.py`) — everything operational. Read live from the DB (through the registry cache); a `PATCH /api/v1/settings` applies to the next run with no restart.

## Environment variables

Sources: `.env.example`, `docker-compose.yml`, `backend/app/config.py`. Compose passes `${VAR:-}` for optional vars; the config module treats blank strings as unset. `quick-setup.sh` manages the three provider keys (chosen via its provider menu, each verified with a free list-models call before saving), `FAKE_LLM_ENABLED`, `REDIS_URL`, and `COMPOSE_PROFILES` in `.env`.

| Variable | Default | Effect | Required? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | *(unset)* | Enables the `anthropic` provider adapter. Gates every `anthropic:*` model. | No — any one provider key (or fake mode) suffices. If unset at first boot, the seed pass resolves `default_model` to the first configured provider's flagship, in this fixed order: `anthropic:claude-sonnet-4-6` → `google_genai:gemini-3.6-flash` → `openai:gpt-5.6-luna` → `fake:scripted` (`_FLAGSHIPS` in `backend/app/seed/loader.py`). An explicitly saved setting is never touched. **The list contains no OpenRouter or custom-gateway entry**, so a fresh install keyed *only* with `OPENROUTER_API_KEY` or `CUSTOM_GATEWAY_*` keeps the unconfigured `anthropic:claude-sonnet-4-6` default and the operator must pick a model in Settings → Models before the first run works |
| `GOOGLE_API_KEY` | *(unset)* | Enables the `google_genai` adapter (chat + embeddings). Presence surfaces the provider in Settings model selects. | No |
| `OPENAI_API_KEY` | *(unset)* | Enables the `openai` adapter (chat + embeddings). | No |
| `FAKE_LLM_ENABLED` | `false` | Enables the scriptable `fake` provider and mounts the `/_fake/script` control router. Combined with the `fake:scripted` model in Settings this gives a fully keyless demo stack. | No — never set it in a normally configured deployment |
| `POSTGRES_USER` | `concierge` | Compose-only: initializes the `db` container and its `pg_isready` healthcheck user. | No (defaults compiled into compose) |
| `POSTGRES_PASSWORD` | `concierge` | Compose-only: `db` container password. | No |
| `POSTGRES_DB` | `concierge` | Compose-only: database name created in the `db` container. | No |
| `DATABASE_URL` | compose: `postgresql+asyncpg://concierge:concierge@db:5432/concierge`; bare config default: `postgresql+asyncpg://postgres:postgres@localhost:5432/concierge` | Backend SQLAlchemy async engine. Also derived from for the LangGraph checkpointer (`+asyncpg` stripped → psycopg pool) and the LISTEN/NOTIFY listener connection (asyncpg). | Effectively yes outside compose defaults |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | `5` / `10` / `30` | M50: the per-replica SQLAlchemy pool budget — pooled ceiling is `DB_POOL_SIZE + DB_MAX_OVERFLOW` connections; `DB_POOL_TIMEOUT` is the seconds a request waits for one before failing. The LangGraph checkpointer pool (10) and the four session connections (the two supervised LISTENs, the control listener, the ambient leader lease) sit outside it: size Postgres `max_connections` from `replicas × (pool + overflow + 10 + 4)` plus a 10-connection reserve — the same arithmetic as the `DB_REPLICAS` row below, which `GET /replicas` → `budget` publishes. Streams (`/chat/stream`, `/ambient/stream`) hold no pooled connection. | Restart |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | `120` / `2` | M51: the per-call timeout and retry budget applied to **every** provider adapter at the port (`port_limits()` in `app/llm/adapters.py`) — the one place a hang or a retry storm is bounded. A provider failure reaches the run as a classified error (rate-limited / timeout / unknown or retired model / provider error) naming the model and the setting that resolved it; `concierge_llm_errors_total{kind}` counts them. | Restart |
| `SHUTDOWN_GRACE_S` | `25` | M51: on SIGTERM the process flips `GET /ready` to 503, refuses new runs (503 + `Retry-After`), waits this long for in-flight runs to finish, then cancels the remainder — each ends `cancelled` with an error naming the shutdown and the grace. The next boot reaps anything still `running`/`queued` as "orphaned by a restart". M53: uvicorn closes the listening socket at SIGTERM *before* the lifespan drain runs and waits up to `--timeout-graceful-shutdown 5` for open connections (sse-starlette ends open streams at once), so the sequence is 5 s + this grace, under the compose `stop_grace_period` of 40 s (Kubernetes: `terminationGracePeriodSeconds`). To let a balancer see the 503 *before* the port closes, send **`SIGUSR1`** first — the pre-stop hook `deploy.sh` uses: readiness flips, new runs are refused, streams the process cannot serve are closed with a reconnect hint, runs executing here keep streaming to their end. | Restart |
| `REPLICA_ID` | container hostname | M54 (spec §18.9): this process's identity — its row in `replicas`, the `owner_replica` stamped on the runs it creates, the origin tag on its control-channel announcements, `concierge_replica_info{replica}`. Leave empty under `--scale`; set it when the orchestrator gives replicas stable names. | Restart |
| `DB_REPLICAS` / `DB_MAX_CONNECTIONS` | `1` / `100` | M54: the declared fleet and the Postgres `max_connections` it must fit in. Per replica the need is `DB_POOL_SIZE + DB_MAX_OVERFLOW + 10 (checkpointer) + 4 (session connections: two supervised LISTENs, the control listener, the leader lease)`, plus a 10-connection reserve for migrations, `psql` and the load harness; `needed = replicas × per_replica + 10`. The arithmetic is logged at boot (`db_connection_budget`, a warning when it does not fit) and served by `GET /replicas`. | Restart |
| `DB_STATEMENT_CACHE_SIZE` | `0` | M54: asyncpg's statement cache and SQLAlchemy's prepared-statement cache on the pooled connections. `0` re-prepares per statement and survives a transaction-mode pooler (pgbouncer), which otherwise fails with `DuplicatePreparedStatementError`; raise it only with no pooler or a session-mode one. The session connections (LISTEN, lease) are direct by design and cannot go through a transaction pooler at all. | Restart |
| `REGISTRY_CACHE_TTL_S` | `300` | M54 (§7.3): every cached registry entry — memory-mode or the redis blob — expires on it, so a lost invalidation costs at most this much staleness. Reloads are additionally generation-guarded (a peer's invalidation landing mid-reload survives it) and `GET /cache/status` reports `dirty` per registry. | Restart |
| `BACKEND_PORT_RANGE` | `8000-8010` | M54 (compose only): the host-port range `docker compose up --scale backend=N` binds, one port per replica (`8000`, `8001`, …) — pin a replica with it, curl its `/replicas`, scrape it. The frontend's nginx resolves `backend` per request through Docker's DNS, so replicas join and leave without a restart. | Recreate |
| `EGRESS_POLICY` / `EGRESS_ALLOW_HOSTS` / `EGRESS_MAX_BYTES` | `public` / *(empty)* / `5242880` | M52: one policy for every outbound fetch the platform makes on someone else's say-so — A2A card fetches and calls, `http_json`/`rss` poll sources, HTTP MCP servers, the webhook channel. `public` refuses loopback, link-local (cloud metadata), private, reserved, multicast and unspecified targets, both by literal address and by what the hostname resolves to — except the hosts you name in `EGRESS_ALLOW_HOSTS` (hosts or `.suffixes`), which are admitted whatever they resolve to: that is how an internal MCP server or agent is named without opening the policy; `allowlist` admits only those hosts; `open` keeps only the caps. Every redirect hop is re-checked (at most five); bodies stream and are cut past `EGRESS_MAX_BYTES`; a refusal has one shape, `egress refused: <kind>`, and `concierge_egress_refused_total{kind}` counts it. Save-time checks at the API are static (scheme, literal address, allowlist); the resolved-address check runs at connect/fetch time. Only http(s) ever passes. | Restart |
| `LANGSMITH_API_KEY` | *(unset)* | LangSmith authentication. Key only — enable/endpoint/project are runtime settings; with the key unset, `langsmith_enabled=true` silently produces no callbacks. | No |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | If set, an OTLP span exporter is attached when the tracer is first created (`backend/app/obs.py`). Unset → spans are created but not exported. | No |
| `WORKSPACE_DIR` | `/workspace` | Sandbox root for the seeded `filesystem` MCP server; compose mounts the `workspace` named volume there and hardcodes the value for the backend service. | No |
| `LOG_LEVEL` | `INFO` | structlog level, applied at process start (`configure_logging`). | No |
| `REDIS_URL` | *(unset)* | Enables the `redis` registry-cache mode (spec §7.3). URL-with-credentials stays env-only; without it, saving `registry_cache_mode=redis` is rejected with 422. `./quick-setup.sh --redis` writes `redis://redis:6379/0`. | Only for redis cache mode |
| `COMPOSE_PROFILES` | *(unset)* | Written by `quick-setup.sh` (`redis` or blank). With `redis`, `docker compose up` also starts the optional `redis:7-alpine` service (bound to `127.0.0.1:6379`). | Only for redis cache mode |
| `BACKEND_PORT` | `8000` | The port the backend is reached on **outside** compose: the fast dev loop's `uvicorn --port`, and what `VITE_API_BASE_URL` points at. **It is not the published host port.** Since M54 compose publishes the backend from `BACKEND_PORT_RANGE` (one port per replica), and `start.sh` / `deploy.sh` / `restore.sh` ask `docker compose port backend 8000` rather than assume the two agree. Changing this alone will not move a conflicting host port. | No |
| `FRONTEND_PORT` | `5173` | Host port mapped to the frontend nginx container's **:8080**. The internal port moved from 80 to 8080 in the M56 hardening wave so the container can run unprivileged; the published host port is unchanged. | Recreate |
| `VITE_API_BASE_URL` | `http://localhost:8000` | **Local dev only**: Vite dev-server proxy target (`frontend/vite.config.ts`). The production image proxies `/api/` and `/metrics` to `backend:8000` via nginx and ignores this variable. | No |
| `OPENROUTER_API_KEY` | *(unset)* | Enables the `openrouter` adapter — one key, many vendors' models through an OpenAI-compatible gateway. **This is the provider every acceptance stage and drill in `docs/acceptance/` ran on** (`openrouter:qwen/qwen3.8-max`). OpenRouter also publishes a per-model price list, refreshed hourly into the cost model. | No |
| `CUSTOM_GATEWAY_BASE_URL` / `CUSTOM_GATEWAY_API_KEY` / `CUSTOM_GATEWAY_MODELS` | *(unset)* | M33 (§18.7): the `custom` provider — any OpenAI-compatible chat-completions endpoint, with **no code change**. `CUSTOM_GATEWAY_MODELS` is a comma-separated list and **is** the validated model list: a `custom:` ref that is not on it is refused at save. Explicit `effort` params are rejected at validation; internal role-default effort hints are dropped at call time. | No |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_TO` | *(unset)* / `25` / … | §18.4 email delivery channel. The channel stays dark unless `SMTP_HOST` **and** `SMTP_FROM`/`SMTP_TO` are set *and* `email` is in `ambient_channels`. A digest batch renders as ONE message. `SMTP_PASSWORD` is a secret: env only, redacted by the sanitizer, never persisted. | Only for the email channel |
| `AMBIENT_WEBHOOK_URL` | *(unset)* | §18.4 webhook delivery channel: the gateway-shaped JSON envelope is POSTed here. **Treat as a secret** — a webhook URL commonly embeds its own token. Judged by `EGRESS_POLICY` like every other outbound fetch, so a loopback or private sink needs `EGRESS_ALLOW_HOSTS`. | Only for the webhook channel |
| `AUTH_ENABLED` | `false` | §18.8: turns the builtin auth provider on. **Dark by default and byte-identical when dark** — single-user, no login, no tenancy filtering. On: `AuthMiddleware` over `/api/v1`, admin-gated registry/settings writes, per-user scoping on every work table. | Restart |
| `AUTH_SESSION_TTL_H` | `24` | §18.8 bearer-session lifetime in hours. Documented since M40 but **not passed into the container until the M56 hardening wave** — a stack older than that silently used the 24 h code default whatever `.env` said. Read directly from the environment by `backend/app/auth/__init__.py`. | Restart |
| `AUTH_PROVIDER` | `builtin` | M55 (§20): the active `AuthProvider` by `provider_id`. The builtin is the §18.8 behaviour; a fork's provider is selected here. An unknown id fails at boot naming the registered ones. | Restart |
| `AUTH_PROVIDER_MODULE` | *(unset)* | A module the auth registry imports before resolving `AUTH_PROVIDER`, so a fork's `@auth_provider` class registers itself from its own file ([extending.md](../extending.md)). | Restart |
| `FRONTEND_ORIGIN` | *(unset)* | CORS. **Unset means permissive** (`allow_origins=["*"]`) — the POC default, appropriate on localhost or a private network. Set it to your admin origin (or a comma-separated list) and CORS is pinned to exactly those. `X-Total-Count` is exposed either way. | Restart |
| `MAX_REQUEST_BYTES` / `MAX_UPLOAD_BYTES` / `MAX_EVAL_ROWS` | `2097152` / `8388608` / `1000` | The inbound caps (`backend/app/limits.py`), applied **unconditionally** — nothing bounded a request body before: not the app, not uvicorn, not nginx. Over the cap is a 413. Not passed through compose today: set them in the container environment if you need to move them. | Restart |
| `MCP_STDIO_ALLOW` | *(unset)* | Comma-separated extra launcher commands a stdio MCP server may spawn, beyond the built-in allowlist. A deployment posture control: an operator, not a registry row, decides what may become a subprocess. | Restart |
| `APP_BUILD` | *(unset)* | Stamped into every run's config snapshot as `snapshot.build`, so a trace names the image it ran on. Nothing sets it in the shipped image, so `build` is `null` unless you pass it (`docker build --build-arg`/`ENV`, or the container environment). | Restart |
| `BACKEND_PORT_RANGE` | `8000-8010` | See the row above — this, **not `BACKEND_PORT`**, is what compose publishes the backend from. | Recreate |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `concierge` ×3 | Compose-only: they initialize the `db` container (rows above). | No |
| `VITE_API_BASE_URL` | `http://localhost:8000` | See the row above — local dev only. | No |

**44 variables are declared in `AppConfig`** (`backend/app/config.py`). Beyond them the deployment reads **ten** more that no `AppConfig` field owns: `AUTH_SESSION_TTL_H`, `MCP_STDIO_ALLOW` and `APP_BUILD` (read straight from `os.environ` at their point of use), `A2A_STUB_API_KEY` (passed into the backend container so a §19 remote agent's `env:NAME` credential can resolve; never referenced statically), `BACKEND_PORT_RANGE` and `COMPOSE_PROFILES` (compose only), `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` (the `db` container's own), and `VITE_API_BASE_URL` (the frontend's Vite dev server). Anything else in the environment is ignored (`extra="ignore"` in `AppConfig`).

`docker-compose.yml` passes **41** entries into the backend service's environment. `MAX_REQUEST_BYTES`, `MAX_UPLOAD_BYTES`, `MAX_EVAL_ROWS`, `MCP_STDIO_ALLOW` and `APP_BUILD` are **not** among them, so they take their code defaults unless you add them to the compose file or the container environment. There is no `env_file:` on the backend service and `.env` is excluded from the build context (`.dockerignore`), so **naming one of those five in `.env` alone does nothing** — only a compose `environment:` entry or the container environment reaches the process. `WORKSPACE_DIR` is hardcoded to `/workspace` for the backend service, so the `.env.example` entry has no effect inside compose. Conversely `LOG_LEVEL` *is* passed through by compose but has no `.env.example` entry, so it is settable and undocumented there.


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
| `registry_cache_mode` | `"memory"` \| `"bypass"` \| `"redis"` | **`"memory"`** | Storage backend of the `RegistryCache` singleton (`registry_cache.py`). **`memory`** is in-process, event-invalidated on every write path, and expires on `REGISTRY_CACHE_TTL_S` so a lost cross-replica NOTIFY costs bounded staleness. **`bypass`** sends every read straight to Postgres — the live-flippable **rollback lever**, not a freshness upgrade: because every write invalidates before returning, a `memory` read is never staler than a bypassed one, so `bypass` buys diagnosis at the cost of a round-trip per registry and settings read, per model call. **`redis`** requires `REDIS_URL` and a successful ping at save (else 422), and fails **open** to Postgres at runtime with `concierge_cache_degraded_total{backend="redis"}` counting. Flips apply live, mid-process; flipping into `memory` warm-loads. (The default was `bypass` through M56 — see `../adr/0004-registry-cache-bypass-default.md`.) |

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

### Admission, limits and guardrails (M40/M51)

| Key | Type | Default | Effect / consumer |
|---|---|---|---|
| `run_max_concurrent` | int ≥ 1 | `8` | the admission semaphore: runs executing at once on this replica (`orchestrator/admission.py`) |
| `run_queue_max` | int ≥ 0 | `32` | queue depth past the semaphore. A run that gets a queue slot is a first-class `queued` row; past the queue, `POST /chat` sheds with 503 + `Retry-After` |
| `run_wall_clock_s` | int ≥ 1 | `900` | every run's ceiling — past it the run ends `failed` with the clock and the setting named |
| `run_stall_after_s` | int ≥ 60 | `300` | the heartbeat window the reaper uses; a silent run ends `stalled` through the normal terminal path |
| `agentic_recursion_limit` | int ≥ 1 | `100` | LangGraph recursion limit for the agentic loop |
| `rate_limit_burst` / `rate_limit_per_s` | int ≥ 1 | `120` / `10` | the §18.8 token bucket, shared across replicas via `rate_buckets`; fails open on a database failure |
| `overlap_threshold_percent` | int 1–100 | `70` | the §4 overlap-guard threshold at which the UI asks to confirm |
| `registry_overlap_audit_enabled` | bool | `false` | the §3.7.1 gate of the periodic registry overlap re-audit (own 6 h clock) |
| `mcp_schema_change_policy` | `warn` \| `quarantine` | `"warn"` | whether a §3.2 schema change also takes the tool out of service until acknowledged |

### HITL

There are no `app_settings` keys for HITL. The HITL queue in Settings is a live view (`GET /api/v1/hitl/pending` — all `paused_hitl` runs), resolved per run via `POST /api/v1/runs/{id}/hitl`.

### Memory (§16) — 22 keys

`memory_enabled` (default **false**) is the master; with it off the run path is byte-identical. Under it: the layer switches `memory_extraction_enabled`, `memory_reflection_enabled`, `procedural_learning_enabled`, and the four consolidation gates `memory_decay_enabled`, `memory_contradiction_enabled`, `memory_communities_enabled`, `memory_compaction_enabled` (**compaction is the one with an irreversible effect** — it hard-deletes folded run digests); the recall dials `memory_recall_top_k` (6), `memory_score_floor` (0.35, absolute similarity), `memory_injection_budget_tokens` (1200), `memory_pinned_budget_tokens` (400), `memory_community_budget_tokens` (150 — **0 skips the rebuild, it does not merely silence the injection**); the write dials `memory_admission_min_confidence` (0.5, walked by the M47 tuner), `memory_quarantine_kinds` (`[]`), `memory_half_life_days` (30), `memory_digest_compact_days` (14), `memory_idle_minutes` (10); forgetting `memory_forget_enabled` (**false**) and `memory_forget_similarity` (0.85); the learner `memory_extraction_learning` (`off` \| `propose` \| `auto`, default **off**); and the role model `memory_extraction_model` (+ `_params`).

### Ambient (§17/§18) — 24 keys

`ambient_enabled` (default **false**) is the master. Under it: `ambient_tick_interval_s` (60); the budgets `ambient_max_routines` (10), `ambient_runs_per_day` (50), `ambient_routine_events_per_hour` (20), `ambient_wakeups_per_routine_per_day` (100), `ambient_escalation_budget_per_day` (10), `ambient_notification_budget_per_day` (3), `ambient_hitl_timeout_h` (24), `ambient_idle_minutes` (10); the delivery policy `ambient_quiet_hours` (`["22:00","07:00"]`), `ambient_digest_times` (`["09:00","17:00"]`), `ambient_timezone` (`UTC` — quiet hours and digest times are wall-clock in this zone), `ambient_interrupt_threshold` (4), `ambient_channels` (`{}` per-tier routing), `ambient_pursuit` (`off` \| `away` \| `always`, default `always` = pre-M41 behaviour); salience `ambient_salience_mode` (default **off**), `ambient_salience_min_urgency` (3), `ambient_salience_model` (+ `_params`); **`ambient_anticipation_enabled`** (default `true`, under the dark master — *the only feature that initiates contact unprompted*, so it is the one to decide about deliberately); and the two learners `ambient_learning_mode` and `ambient_salience_learning` (both `off` \| `propose` \| `auto`, both default **off**), with `ambient_precision_rule_enabled` (true) for the rule-based precision downgrade.

### A2A (§19) — 7 keys

`a2a_enabled` (default **false**) is the master: dark means 409 on registry writes, inert tools and byte-identical runs. Under it: `a2a_card_refresh_interval_s` (300), `a2a_task_timeout_s` (120), `a2a_http_timeout_s` (15), `a2a_poll_interval_s` (60 — the parked-task poller's effective cadence is `max(tick, interval)`), `a2a_max_parked` (20 — **0 disables parking**, and a timeout becomes a plain tool error), `a2a_fence_max_chars` (8000).

### Evals (§15)

| Key | Type | Default | Effect / consumer |
|---|---|---|---|
| `evals_enabled` | bool | `true` | the §3.7.1 gate of the whole eval surface; off means `POST /evals/datasets/{id}/run` 409s |
| `eval_judge_model` (+ `_params`) | `provider:model` \| null | `null` | the `llm_judge` grader's model; null falls back to `default_model`. The UI hints when the judge is the model being evaluated |

**122 settings keys total** — `DEFAULTS` in `backend/app/settings_store.py` is the source of truth, and a test asserts that every live key has a Settings control, so a key added without one fails the suite rather than a review. The sections above are grouped by family rather than listing every key individually; `GET /api/v1/settings` returns the merged object.

### Retention, cost and MCP reconnection (M53)

| Key | Type / values | Default | Effect / consumer |
|---|---|---|---|
| `retention_<table>_enabled` for the **nine** gated tables — `ambient_events`, `deliveries`, `ambient_policies`, `pattern_instances`, `a2a_tasks`, `auth_sessions`, and the run ledger `checkpoints`, `run_steps`, `runs` (`RETENTION_TABLES` in `app/retention.py`) | boolean | `false` for eight, `true` for `auth_sessions` | the gate of that table's purge, enforced inside the purge — off means nothing is deleted, whoever calls it. Deleting is irreversible, so every gate but the expired-session sweep is born off (the login path already swept expired sessions) |
| `retention_<table>_days` | integer 1–3650 | 30 / 90 / 365 / 7 / 90 / 7 / 7 / 30 / 90 (in the table order above) | the window: only rows the system is finished with AND older than this are eligible — processed events, delivered or superseded deliveries, superseded policy rows (never the newest per category), matched/expired pattern instances, terminal A2A tasks, sessions past expiry, and for the run ledger the checkpoints/steps/runs of a **terminal** run (never a `queued`, `running` or `paused_hitl` one, at any age). The run ledger is purged narrowest-first (checkpoints → steps → runs) so nothing is orphaned. `GET /retention` previews the eligible counts; `POST /retention/run` runs now; the periodic loop runs hourly under advisory lock `427018`, in batches of 5000 (500 for the run ledger, since each run drags its steps and checkpoints). Full table: [`data-lifecycle.md`](./data-lifecycle.md) |
| `mcp_auto_reconnect_enabled` | boolean | `true` | a server that fails to connect or fails a health ping is retried with backoff (5 s doubling to 5 min). Off: it stays `error` until reconnected by hand |
| `mcp_reconnect_max_attempts` | integer 1–100 | `8` | consecutive failures before the circuit opens; the row's `last_error` says so and the reconnect button resets it |
| `model_prices` | object `{"provider:model": {"input_per_m", "output_per_m"}}` | `{}` | USD per million tokens; an override wins over a provider-reported price (OpenRouter publishes one per model, refreshed hourly) and the built-in reference table (`app/llm/pricing.py`). A model none of them know is unpriced — reported, never guessed |
| `spend_ceiling_enabled` | boolean | `false` | the gate of the shared spend ceiling; off is the pre-M53 admission, byte-identical |
| `spend_ceiling_usd_per_day` | number > 0 | `10.0` | one ceiling across every run kind (chat, direct, ambient, eval), summed from the database over the UTC day so every replica sees the same number. Past it: chat 429 + `Retry-After`, ambient fire held on its event with the reason, eval batch stops. `GET /spend` reports the day |

## Live vs restart

Verified against the code, not assumed:

- **Live (every one of the 122 keys)**: each is read from the DB (through the cache, which the settings write path invalidates) at its point of use — run creation, planner call, dispatch, tool-loop construction, admission, MCP health cycle, cache access, retrieval, answer-UI generation, the ambient tick, the memory jobs, LangSmith callback construction. A PATCH takes effect on the next run (or the next loop cycle for the tick/health/job keys, the next model call for cache/retrieval keys) with no restart. `registry_cache_mode` re-applies itself mid-process via the cache's own settings invalidation hook.
- **What a PATCH does *not* do** is change an in-flight run: a run's `snapshot` freezes the settings it was dispatched under, so its trace reads against what it actually ran with. Two keys are bounded by their loop rather than the run: `ambient_tick_interval_s` takes effect on the next tick, `mcp_health_interval_s` on the next ping cycle.
- **`log_level` and `otlp_endpoint`** apply even faster than "next run": the settings write path calls their consumers directly (`configure_logging` / `apply_otlp_endpoint` in `settings_store.update_settings`), so they take effect the moment the PATCH returns. The env vars (`LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`) are bootstrap defaults only; an explicitly stored setting is re-applied over them at startup, and a never-touched setting leaves the env value in charge.
