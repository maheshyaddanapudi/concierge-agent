# REST API Reference

The Concierge Agent backend is a single FastAPI process. All application routers are mounted under the **`/api/v1`** prefix (`backend/app/main.py`, `backend/app/api/__init__.py`): **89 paths, 118 operations** across 20 mounted routers (17 modules — `ambient.py` contributes three and `routines.py` two). Three operational endpoints — `/health`, `/ready` and `/metrics` — live at the application root, *outside* `/api/v1`.

The authority is the running process: `GET /openapi.json` (or `/docs`) enumerates every path this page describes. If the two ever disagree, the OpenAPI document is right and this page is stale.

Interactive OpenAPI documentation is served by FastAPI at **`/docs`** on the running backend (e.g. `http://localhost:8000/docs` on a `docker compose up` stack).

Related documents: [SSE event stream](sse-events.md) · [Workflow DSL](workflow-dsl.md) · [Skill document format](skill-format.md)

## Conventions

- **Content type**: JSON request and response bodies (`application/json`), except `GET /api/v1/chat/stream/{run_id}` (`text/event-stream`, see [sse-events.md](sse-events.md)) and `GET /metrics` (Prometheus text format).
- **Error envelope**: every error is FastAPI's standard shape — `{"detail": <string or validation array>}`. Application errors raised via `HTTPException` carry a human-readable string in `detail`; Pydantic request-validation failures carry FastAPI's structured array. Multiple application validation errors are joined into one string with `"; "` (see `backend/app/api/skills.py`, `backend/app/api/settings.py`).
- **Request models forbid unknown fields**: all input schemas extend `ApiModel` with `extra="forbid"` (`backend/app/schemas/common.py`), so an unrecognized body field is a 422 — including any attempt to send `id` in a PATCH. **Registry `id`s are immutable**: no write schema accepts one.
- **Soft delete**: registry DELETEs set `deleted_at`; deleted records 404 on subsequent GET/PATCH (`fetch_or_404` in `backend/app/api/deps.py`).

### Status codes used by this API

| Code | Meaning here |
|------|--------------|
| 200 | Success. |
| 201 | Created — registry POSTs, `POST /chat`, `POST /runs/{id}/retry`, `POST /conversations`. |
| 204 | Success, no body — DELETEs. |
| 403 | **Static-record guard**: PATCHing any field of a `source: "static"` record other than `status`/`direct_exposure` (`enforce_static_rules`, `backend/app/api/deps.py`); DELETEing a static record (`reject_static_delete`); PATCHing `workflow`/`persona` of a `kind: "native"` sub-agent. |
| 404 | Record not found or soft-deleted. Also returned by the `/_fake/*` endpoints when `FAKE_LLM_ENABLED` is not set (the router hides itself). |
| 409 | Conflict: HITL decision posted to a run that is not `paused_hitl`; cancel/retry of a run in the wrong state; delete of a `running` run; delete of a tool/skill/MCP server that other records still bind; `tool_key` collision on tool PATCH. |
| 422 | Validation: Pydantic request-shape errors; empty chat message; unknown/inactive `tool_ids` on skill save; `{tool:...}` mention of an unbound tool; invalid `model`/`model_params` selection; workflow DAG validation and compile failures ([workflow-dsl.md](workflow-dsl.md)); settings validation — including `registry_cache_mode: "redis"` without `REDIS_URL` set in the environment (`backend/app/settings_store.py`); unknown registry name on `POST /cache/refresh/{registry}`. |
| 401 | Auth is on and the request carries no valid bearer session. `AuthMiddleware` guards only paths under `/api/v1`, and exempts exactly two of them: `POST /auth/login` and `POST /routines/{id}/fire` (the fire token *is* its auth). The root endpoints `/health`, `/ready` and `/metrics` are never guarded because they are outside the prefix, not because they are listed. |
| 403 | Also: a non-admin principal attempting a registry or settings write when auth is on. |
| 413 | Request body over `MAX_REQUEST_BYTES`, or an upload over `MAX_UPLOAD_BYTES` / `MAX_EVAL_ROWS`. |
| 429 | Rate limit (`rate_limit_burst` / `rate_limit_per_s`) or the spend ceiling; both carry `Retry-After`. |
| 503 | MCP manager not running (reconnect/refresh-tools during startup/shutdown); admission shed on `POST /chat` when the run queue is full (with `Retry-After`); `GET /ready` while draining or when the database does not answer. |

### Common list query parameters

All registry list endpoints (`/tools`, `/skills`, `/sub-agents`, `/mcp-servers`) accept (`backend/app/api/deps.py`):

| Param | Type | Meaning |
|-------|------|---------|
| `include_deleted` | bool, default `false` | Include soft-deleted records. |
| `source` | `static` \| `dynamic` | Filter by record source. |
| `q` | string | Case-insensitive substring match on `name` or `description`. |

### Static-record rules (spec §4)

Records with `source: "static"` (native tools, native skills, seeded sub-agents/servers) are code- or seed-defined:

- **Definition writes are rejected with 403.** Only `status` and `direct_exposure` are togglable (`STATIC_TOGGLABLE` in `backend/app/api/deps.py`).
- **Deletes are rejected with 403** — toggle `status` to `"inactive"` instead.
- `kind: "native"` sub-agents additionally reject `workflow`/`persona` changes even where the record is not static.

---

## Settings router — `backend/app/api/settings.py`

| Method + path | Purpose |
|---|---|
| `GET /api/v1/settings` | Merged settings view: defaults overlaid with stored rows. Returns the full settings object (keys listed in `DEFAULTS`, `backend/app/settings_store.py`). |
| `PATCH /api/v1/settings` | Partial update; body is `{key: value, ...}`. 422 with joined error string on any invalid key/value. Selecting `registry_cache_mode: "redis"` requires `REDIS_URL` (422 otherwise) and pings Redis at save time (422 `redis unreachable: ...` on failure). Returns the merged settings. |
| `GET /api/v1/providers` | Read-only provider adapter panel: `[{provider_id, configured, models: [{id, display_name, supports_effort, supports_temperature, supports_max_output_tokens}]}]`. API keys are env-only and never appear here. |
| `GET /api/v1/hitl/pending` | All runs currently `paused_hitl`, across every conversation: `[{run_id, conversation_id, chat_message, started_at}]`. |

There are **122** settings keys; every one is enumerated with its type, default, effect and consumer in [operations/configuration.md](../operations/configuration.md), and `DEFAULTS` in `backend/app/settings_store.py` is the source both are checked against. The eight **model roles** — `default_model`, `planner_model`, `aggregator_model`, `formatter_model`, `overlap_judge_model`, `eval_judge_model`, `memory_extraction_model`, `ambient_salience_model` (each with a `*_params` sibling) — all fall back to `default_model` when null, and `PATCH` refuses a null `default_model`, params without their model ref, and a bool where an int is expected.

## Tools router — `backend/app/api/tools.py` (prefix `/tools`)

Tools are **never created via API** — they come from MCP ingestion or the native `@native_tool` startup scan.

| Method + path | Purpose | Key request fields | Errors |
|---|---|---|---|
| `GET /tools` | List tools (common filters). | — | — |
| `GET /tools/{tool_id}` | One tool. | — | 404 |
| `PATCH /tools/{tool_id}` | Edit `description`, `status`, `direct_exposure`, `tool_key`. | `ToolPatch` | 403 static guard (only `status`/`direct_exposure` on static); 409 `tool_key` already in use |
| `GET /tools/{tool_id}/skills` | Skills bound to this tool. | — | 404 |
| `POST /tools/{tool_id}/acknowledge-schema` | Operator has read a §3.2 schema change: clears `schema_changed_at` and, when the tool was quarantined, returns it to service. The version and hash stay — they are the record. | — | 404 |
| `POST /tools/{tool_id}/restore` | Undo a soft delete (M53) — since re-ingest no longer resurrects a deleted MCP tool, restoring one is an explicit operator act. | — | 404 |
| `DELETE /tools/{tool_id}` | Soft-delete a dynamic tool. | — | 403 static; 409 if bound to skills (`"tool is bound to skills: ..."`) |

`ToolOut` fields: registry base (`id`, `name`, `description`, `source`, `status`, `created_at`, `updated_at`, `deleted_at`) + `kind` (`mcp` / `native` / `a2a`), `mcp_server_id`, `remote_agent_id`, `tool_name`, `native_ref`, `tool_key`, `direct_exposure`, `input_schema`, `schema_hash`, `schema_version`, `schema_changed_at`, `ingest_state`, `description_source`.

## Skills router — `backend/app/api/skills.py` (prefix `/skills`)

| Method + path | Purpose | Key request fields | Errors |
|---|---|---|---|
| `GET /skills` | List skills (common filters). | — | — |
| `POST /skills` | Create a custom skill (201). | `name`, `description`, `persona`, `instructions`, `tool_ids: [UUID]`, `direct_exposure`, `model`, `model_params`, `max_tool_iterations` | 422: unknown/inactive tool id; `model_params` without `model`; invalid model selection; `{tool:...}` mention not in bound tools |
| `POST /skills/check-overlap` | Advisory pre-save LLM-as-judge duplicate check — never blocks. | `name`, `description`, `instructions`, `tool_ids`, `exclude_id` | — |
| `GET /skills/{skill_id}` | One skill (embeds bound `tools`). | — | 404 |
| `PATCH /skills/{skill_id}` | Partial update; re-validates tools/model/mentions on touched fields. | `SkillPatch` (adds `status`) | 403 static guard; 422 as on create |
| `GET /skills/{skill_id}/sub-agents` | Sub-agents whose workflows use this skill. | — | 404 |
| `POST /skills/overlap-ack` | Record that the operator saved past a flagged overlap (204) — content-free: the draft type and the percentage, never the text. | `{draft_type: "skill"\|"sub_agent", overlap_percent}` | 422 |
| `DELETE /skills/{skill_id}` | Soft-delete. | — | 403 static; 409 if referenced by active sub-agents |

Overlap check response (`OverlapCheckOut`, `backend/app/overlap.py`): `{overlap, threshold, overlap_percent, match_type, match_id, match_name, reasoning, judge_available}`. **`judge_available: false` means the judge could not be reached or its verdict could not be parsed** — the 0 % it reports alongside is not a real 0 %, and a caller must say so rather than present it as a clean result (the UI shows a "Saved unjudged" notice).

See [skill-format.md](skill-format.md) for the `.skill.md` document shape these fields mirror.

## Sub-agents router — `backend/app/api/sub_agents.py` (prefix `/sub-agents`)

| Method + path | Purpose | Key request fields | Errors |
|---|---|---|---|
| `GET /sub-agents` | List sub-agents (common filters). | — | — |
| `POST /sub-agents` | Create a custom sub-agent (201). The workflow is structurally validated **and** factory-compiled at save time. | `name`, `description`, `persona`, `model`, `model_params`, `workflow` ([workflow-dsl.md](workflow-dsl.md)) | 422: workflow validation/compile errors (joined string); invalid model fields |
| `POST /sub-agents/check-overlap` | Advisory pre-save duplicate check. | `name`, `description`, `skill_ids`, `exclude_id` | — |
| `GET /sub-agents/{agent_id}` | One sub-agent (embeds `skills`, `workflow`). | — | 404 |
| `PATCH /sub-agents/{agent_id}` | Partial update; workflow changes re-validate and re-resolve skills. | `SubAgentPatch` (adds `status`) | 403 static guard; 403 `workflow`/`persona` on `kind: "native"`; 422 as on create |
| `POST /sub-agents/{agent_id}/validate` | Dry-run factory compile. | — | 404. Returns `{valid, errors: []}` (native agents are always `valid: true`) |
| `POST /sub-agents/{agent_id}/invoke` | Direct invocation (§7.5, 201): pin this sub agent, skip routing. The run keeps the full lifecycle — SSE, HITL, formatter, trace, metrics under `mode='direct'`. | `{message, conversation_id?, include_history_summary?, include_memories?}` → `{run_id, conversation_id}` | 404; **409** the agent is not `active`; **403** `direct_exposure` is off; 422 empty message, or `include_memories`/`include_history_summary` without a `conversation_id` |
| `DELETE /sub-agents/{agent_id}` | Soft-delete. | — | 403 static |

## MCP servers router — `backend/app/api/mcp_servers.py` (prefix `/mcp-servers`)

| Method + path | Purpose | Key request fields | Errors |
|---|---|---|---|
| `GET /mcp-servers` | List servers; each row carries `tool_count`. | — | — |
| `POST /mcp-servers` | Register a server (201) as `status: "inactive"`; the MCP manager connects it asynchronously and flips status to `active`/`error`. | `name`, `description`, `transport` (`stdio`\|`http`), `command`+`args`+`env` (stdio), `url`+`headers` (http) | 422: `stdio` without `command`, `http` without `url` |
| `GET /mcp-servers/{server_id}` | One server. | — | 404 |
| `PATCH /mcp-servers/{server_id}` | Edit definition or toggle `status`. | `McpServerPatch` | 403 static guard |
| `DELETE /mcp-servers/{server_id}` | Soft-delete server **and its ingested tools**; disconnects. | — | 403 static; 409 if its tools are bound to skills |
| `POST /mcp-servers/{server_id}/reconnect` | Force a reconnect attempt. | — | 404; 503 manager not running |
| `POST /mcp-servers/{server_id}/refresh-tools` | Re-ingest the server's tool list. | — | 404; 503 manager not running |

`McpServerOut` adds `transport`, `command`, `args`, `env`, `url`, `headers`, `last_connected_at`, `last_error`, `tool_count`.

## Chat router — `backend/app/api/chat.py`

| Method + path | Purpose | Key request/response fields | Errors |
|---|---|---|---|
| `GET /conversations` | List conversations newest-first: `[{id, title, created_at, updated_at, run_count}]`. | — | — |
| `POST /conversations` | Create a conversation (201): `{id, title}`. | `{title?}` | — |
| `GET /conversations/{id}` | Conversation detail: `{id, title, messages, runs}`. `messages` interleaves `user` / `assistant` / `error` roles (failed and cancelled runs keep their error in place); assistant messages carry `answer_ui`. | — | 404 |
| `POST /chat` | Start a run (201). Omitting `conversation_id` creates a conversation from the message. The run executes as an asyncio task in-process. | Request `{conversation_id?, message}` → `{run_id, conversation_id}` | 422 empty message |
| `GET /chat/stream/{run_id}` | SSE event stream: full history replay, then live events. See [sse-events.md](sse-events.md). | — | 404 run not found |
| `POST /runs/{run_id}/hitl` | Resolve the pending HITL gate and resume from checkpoint. | `{decision: "approve"\|"deny", note?, answers?: {question_id: value}}` → `{status: "resuming", decision}` | **409 if the run is not `paused_hitl`** (`"run is <status>, not paused_hitl"`) |

## Runs router — `backend/app/api/runs.py` (prefix `/runs`)

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /runs` | All runs, newest-first. Each: `{id, conversation_id, chat_message, status, orchestrator_mode, plan, snapshot, final_answer, answer_ui, error, started_at, finished_at, total_input_tokens, total_output_tokens}`. | — |
| `GET /runs/{run_id}` | Run detail — M54 adds `owner_replica` (the replica executing it) and `cancel_requested_at` — including ordered `steps`: `[{id, parent_step_id, sub_agent_id, node_id, step_type, input, output, model, input_tokens, output_tokens, status, started_at, finished_at, error}]`. | 404 |
| `POST /runs/{run_id}/cancel` | Cooperative cancel; cancelling a `paused_hitl` run resolves it as `cancelled`. Returns the run's **real** status: `200 {status: "cancelled"}` when this replica executed the run (or nothing anywhere could be executing it). M54 (spec §18.9): when the run is executing on another replica the cancel is a persisted intent — `runs.cancel_requested_at` plus a control-channel announcement the owner acts on at once (its heartbeat is the fallback) — and the response is `200 {status: "cancelled"}` if the owner acted within ~3 s, else **`202 {status: "cancel_requested"}`**; poll `GET /runs/{run_id}`. A cancel never writes a terminal status the answering replica cannot make true. | 409 unless the run is `running`, `queued` or `paused_hitl` |
| `POST /runs/{run_id}/retry` | Re-plan a **failed** run from its original message (201): `{run_id, conversation_id}` for the new run. | 409 `"only failed runs can be retried"` |
| `DELETE /runs/{run_id}` | Hard-delete one run and its steps; also drops its SSE history. | 404; 409 if `running` (`"cancel the run before deleting it"`) |
| `DELETE /runs` | Purge all run history (runs + steps + SSE event buffers). 204. | — |

Run `status` values: **`queued`**, `running`, `paused_hitl`, `completed`, `failed`, `cancelled`, **`stalled`**. `queued` (M51) means admission is full and the run holds a queue slot; `stalled` means the heartbeat reaper ended a run whose task went silent. A client deciding what is still live should treat `queued`, `running` and `paused_hitl` as live.

`step_type` values on a run's steps: `plan`, `route`, `skill`, `hitl`, `tool_call`, `aggregate`, **`format`** (the formatter's own call) and **`summary`** (the §7.5 history-summary call).

`GET /runs` is **paged**: `limit` (1–500, default 50) and `offset`, with the total in the `X-Total-Count` response header (exposed through CORS), ordered newest-first with the id as the tiebreaker so no row lands on two pages. `routine_id` filters to a routine's own run history. The list returns a light projection — the heavy columns (`plan`, `snapshot`, `answer_ui`, and the steps) come from `GET /runs/{run_id}`.

## Auth router — `backend/app/api/auth.py` (prefix `/auth`, §18.8 / §20)

Dark unless `AUTH_ENABLED=true`: with auth off, `POST /auth/login` returns **409** and every other surface behaves as single-user. The active provider is chosen by `AUTH_PROVIDER` (`builtin` by default) — a fork's provider is selected by `AUTH_PROVIDER_MODULE` ([extending.md](../extending.md)).

| Method + path | Purpose | Errors |
|---|---|---|
| `POST /auth/login` | Exchange credentials for a bearer session. The bootstrap admin's one-time password is printed once at boot. Sessions live `AUTH_SESSION_TTL_H` hours and are sha256-hashed at rest. | 409 auth dark; 401 bad credentials |
| `POST /auth/logout` | Invalidate this session (204). | — |
| `GET /auth/me` | The current principal: `{user_id, username, role, prefs}`; `{authenticated: false}` when auth is dark. | — |
| `PATCH /auth/me/prefs` | Update this principal's stored preferences. | 401 |
| `GET /auth/users` | List identities (admin). | 401; 403 non-admin |
| `POST /auth/users` | Create an identity (201, admin). | 401; 403 non-admin |

`AuthMiddleware` (`backend/app/auth/__init__.py`) guards **only paths that start with `/api/v1`**, and within that prefix it exempts exactly **two**, by the regex `^/api/v1/(auth/login$|routines/[0-9a-f-]+/fire$)`: `POST /auth/login`, and `POST /routines/{id}/fire`, where the fire token **is** the auth. The root endpoints `/health`, `/ready` and `/metrics` need no exemption — they are outside the prefix the middleware inspects. With `AUTH_ENABLED` off the middleware short-circuits before any check, so the unauthenticated deployment is byte-identical. `GET /chat/stream/{id}` and `GET /ambient/stream` additionally accept `?token=`, because `EventSource` cannot set headers.

## Memories router — `backend/app/api/memories.py` (prefix `/memories`, §16)

Inert while `memory_enabled` is off.

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /memories` | List memories. Query: `scope`, `kind`, `status` (`active` / `quarantined` / `superseded` / `expired`), `source`, `conversation_id`, `q`, `limit` (≤ 500, default 100). | — |
| `POST /memories` | Write a memory by hand (201) — the same admission gate every machine write passes. | 422 validation; 409 suppressed by a tombstone |
| `GET /memories/status` | The layer's state: counts by kind and status, the active embedding model key, the backfill's outstanding rows. | — |
| `GET /memories/recall` | Run the §16 hybrid recall for a query, as the injector would: `q` (required), `scope`, `kinds` (comma-separated), `conversation_id`, `k` (≤ 50, default 6), `floor` (0–1 absolute-similarity cut), `as_of` (bi-temporal "what did we believe on date X"). Inspection never bumps the rehearsal stats. | 422 |
| `GET /memories/{memory_id}` | One memory with its supersession chain and provenance. | 404 |
| `PATCH /memories/{memory_id}` | Edit text/kind/confidence, approve or reject a quarantined one, pin a profile fact. | 403 on a machine-owned field; 404 |
| `DELETE /memories/{memory_id}` | **Two verbs** via `?mode=`: `forget` leaves a content-free tombstone that suppresses re-admission, `erase` (the default) is physical with no trace. 204. | 404 |
| `GET /memories/tombstones` | The Forgotten list — **metadata only**, there is no text to show. | — |
| `DELETE /memories/tombstones/{tombstone_id}` | Unforget: drop the tombstone, the fact becomes learnable again (204). | 404 |
| `POST /memories/purge` | §8.7 data purge, memory half: clears the semantic store, its embeddings and the tombstones (204). Episodic tables cascade with the run purge. | — |

## Routines and presence — `backend/app/api/routines.py` (§17)

Writes return **409 while `ambient_enabled` is off**.

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /routines` | List routines with trigger, allowlist, cadence state and quarantine reason. | — |
| `POST /routines` | Create a routine (201). Triggers are typed at the boundary: `interval` ≥ 60 s, parseable `cron`, ISO `once.at`, webhook filters with known operators and compiling regexes; quiet-hours and digest-time strings are `HH:MM`-bounded. | 409 ambient dark; 422 trigger/model/allowlist validation |
| `GET /routines/{routine_id}` | One routine. | 404 |
| `PATCH /routines/{routine_id}` | Partial update, same validation; clearing `status_reason` un-quarantines. | 404; 409; 422 |
| `DELETE /routines/{routine_id}` | Delete (204). | 404 |
| `POST /routines/{routine_id}/token` | Issue or rotate the fire token — **shown once**, only its hash is stored. | 404 |
| `DELETE /routines/{routine_id}/token` | Revoke the token (204). | 404 |
| `POST /routines/{routine_id}/fire` | Fire the routine (202). Authenticated by the fire token alone (`Authorization: Bearer <token>`), which is why this path is exempt from `AuthMiddleware`. The event enters the decision plane and may be held rather than fired — the response says which. | 401 wrong/absent token; 404; 409 ambient dark |
| `POST /presence/heartbeat` | Report this client's presence — the input to the idle detector and the pursuit oracle. | — |
| `GET /presence` | The current presence snapshot. | — |

## Ambient routers — `backend/app/api/ambient.py` (§17.5 / §17.6 / §8.9)

Three routers: `/deliveries` (the outbox), `/watches` (standing intents) and `/ambient` (the ledger and the stream).

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /deliveries` | The Inbox: rows with tier, urgency, `skey` lineage, `seen_at`, the per-channel send ledger and any salience verdict. Query: `status` (`all` — the default — / `pending` / `delivered`), `limit` (capped at 500). Returns `{items: [...]}`. | — |
| `GET /deliveries/unread-count` | The nav badge: delivered-but-never-opened items. Pending rows are not yet news and do not count. | — |
| `GET /deliveries/digest-preview` | What the next digest flush would contain, in flush order. | — |
| `POST /deliveries/{delivery_id}/seen` | Stamp `seen_at` — what turns "was it attended to" from an inference into a fact. | 404 |
| `POST /deliveries/{delivery_id}/feedback` | Capture `accepted` / `dismissed` and persist the blended §17.7 reward. | 404; 422 unknown verdict |
| `POST /deliveries/{delivery_id}/salience/{action}` | Act on a §17.5 verdict: `apply`, `decline`, or `undo` one already applied (restores the pre-mutation snapshot; refuses honestly once a digest has spent the escalation). First-write-wins. | 404; 409 already decided |
| `GET /watches` | Standing intents with their compiled rules and cadence state. | — |
| `POST /watches/compile` | NL → typed rule through the **same** compiler `ambient.watch` uses; returns the rule for an explicit confirm. | 409 ambient dark; 422 uncompilable |
| `POST /watches` | Create a typed event-filter watch directly from filter rows (201) — no compiler; still lands `proposed` for an explicit confirm. | 409; 422 |
| `PATCH /watches/{intent_id}` | Confirm, pause, retire or re-scope a watch. | 404; 422 |
| `GET /ambient/ledger` | The append-only fire/hold audit, newest first. Query: `limit` (default 100), `verdict` (`all` / `fire` / `hold`), `correlation_id` to pull one chain. | — |
| `GET /ambient/precision` | Per-category intervention precision plus the active policy override. | — |
| `GET /ambient/policies` | The append-only policy ledger, newest first (§17.6 audit + revert). | — |
| `POST /ambient/policies/{policy_id}/approve` | Approve a queued learner proposal (`propose` mode). | 404; 409 not pending |
| `POST /ambient/policies/{policy_id}/reject` | Reject one — captured, never applied. | 404; 409 |
| `POST /ambient/policies/revert` | One-click revert: append a clearing row for the category. History stays; the override stops applying. | 422 unknown category |
| `GET /ambient/stream` | Global delivery-event SSE (§18.4). **409 while ambient is dark**, and it closes itself if ambient goes dark under it. Accepts `?token=`. | 409 |

## Remote agents router — `backend/app/api/remote_agents.py` (prefix `/remote-agents`, §19)

Writes return **409 while `a2a_enabled` is off**; the projected `kind='a2a'` tools are inert.

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /remote-agents` | List counterparties (common registry filters) with card summary and `auth_status`. | — |
| `POST /remote-agents` | Register by Agent Card URL (201): the manager fetches `/.well-known/agent-card.json`, stores the card and projects each card skill as a tool. | 409 a2a dark; 422 card fetch/parse; egress refusal |
| `GET /remote-agents/{agent_id}` | One agent with its card, skills and per-scheme `configured` flags. | 404 |
| `PATCH /remote-agents/{agent_id}` | Edit the definition, credentials (**write-only**: `***` keeps, null removes, `env:VAR` resolves at connect time) or `status`. Deactivating takes its tools out of the catalog under `ingest_state='agentoff'`. | 403 static; 404; 422 |
| `POST /remote-agents/{agent_id}/refresh-card` | Re-fetch and reconcile the card now. A refresh **never re-enables** an agent an operator disabled. | 404; 422 |
| `GET /remote-agents/{agent_id}/tasks` | The task drawer: outbound tasks with state, park status and the last polled result. | 404 |
| `POST /remote-agents/{agent_id}/tasks/{task_id}/reply` | Answer a remote `input-required` question. Terminal → an outbox delivery; still working → re-parked; another question → stays in the drawer. | 404; 409 wrong state |
| `POST /remote-agents/{agent_id}/tasks/{task_id}/cancel` | Propagate `tasks/cancel` to the counterparty. | 404; 409 |
| `DELETE /remote-agents/{agent_id}` | Soft-delete the agent and its projected tools (204). | 403 static; 409 if its tools are bound to skills |

## Evals router — `backend/app/api/evals.py` (prefix `/evals`, §15)

Inert while the §3.7.1 eval gate is off.

| Method + path | Purpose | Errors |
|---|---|---|
| `POST /evals/datasets` | Upload a dataset (201) as csv or xlsx in the predefined format. Bounded by content type, `MAX_UPLOAD_BYTES` and `MAX_EVAL_ROWS`. | 413 too large / too many rows; 422 bad format; 422 a case with a blank expectation |
| `GET /evals/datasets` | List datasets with case counts. | — |
| `GET /evals/datasets/{dataset_id}` | One dataset with its cases. | 404 |
| `DELETE /evals/datasets/{dataset_id}` | Delete a dataset and its cases (204). | 404 |
| `POST /evals/datasets/{dataset_id}/run` | Start a batch (201). Every case is an ordinary Run tagged `is_eval`, with HITL auto-approved; the batch is **fully isolated** — no memory, presence, wakeups or HITL queue — and gate auto-approval needs per-dataset opt-in. | 404; 409 gate off; 429 spend ceiling |
| `GET /evals/runs` | List batches (optionally `?dataset_id=`). | — |
| `GET /evals/runs/{eval_run_id}` | One batch with its config snapshot and **paged** results: per case the grade (`exact` / `contains` / `llm_judge`), the judge's structured verdict, and the underlying `run_id`. A judge failure grades the case `error`, never `pass`. | 404 |
| `POST /evals/runs/{eval_run_id}/cancel` | Stop a batch. The per-case reaper ends a case that outlives its budget; the underlying run is left to its own wall clock. | 404; 409 already terminal |

## Ops router — `backend/app/api/ops.py`

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /retention` | Per table: its gate, its window and how many rows a purge would delete **right now** — counted whether or not the gate is on, so the preview is honest before anything is enabled. | — |
| `POST /retention/run` | Run every purge now. Each still answers to its own gate, enforced inside the purge. | — |
| `GET /spend` | The UTC day's priced spend across every run kind, the ceiling and whether it is reached. A model with no known price is reported **unpriced**, never guessed. | — |
| `GET /replicas` | The fleet as the database sees it (see **Fleet (M54)** below). | — |

## Cache router — `backend/app/api/cache.py` (prefix `/cache`)

| Method + path | Purpose | Errors |
|---|---|---|
| `GET /cache/status` | Registry cache status: `{mode: "bypass"\|"memory"\|"redis", registries: {tools\|skills\|sub_agents\|settings: {records, generation, loaded_at, cached}}}`. In `bypass` mode `records`/`loaded_at` are `null` and `cached` is `false`. | — M54: each registry entry also reports `dirty` — a generation bumped by an invalidation whose data has not been reloaded yet is visible rather than hidden behind a healthy-looking counter. |
| `POST /cache/refresh/{registry}` | Operator-forced eager reload of one registry (`tools`, `skills`, `sub_agents`, `settings`) or `all`. | 422 `unknown registry '<x>'; one of [...]/all` |

## Seed router — `backend/app/api/seed.py`

| Method + path | Purpose |
|---|---|
| `POST /seed/reload` | Idempotent re-run of the startup seed (native tools, `.skill.md` skills, seeded sub-agents), then invalidates every cache registry. Returns `{status: "ok", ...summary counts}`. |

## Fake-LLM router — `backend/app/api/fake_llm.py` (prefix `/_fake`, flag-gated)

Demo/testing only. Every endpoint returns **404** unless the `FAKE_LLM_ENABLED` environment variable is set (`backend/app/config.py`) — the router is invisible in normal deployments. Lets an external driver queue deterministic fake-model responses for keyless demos and the acceptance walk.

| Method + path | Purpose | Request | Response |
|---|---|---|---|
| `POST /_fake/script` | Queue scripted model responses in order. | `{calls: [{content?, tool_calls?, error?, delay_s?}]}` — `error` queues a raised `RuntimeError`; otherwise an AI message with optional tool calls and delay. | `{queued, pending}` |
| `POST /_fake/clear` | Drop any queued script. | — | `{pending: 0}` |

## Root endpoints — `backend/app/main.py` (no `/api/v1` prefix)

| Method + path | Purpose |
|---|---|
| `GET /health` | **Liveness only**: `{"status": "ok"}`. Never probes a dependency — a replica whose database is away must not be killed for it, only taken out of rotation. |
| `GET /ready` | **Readiness** (M51/M53): 200 `{status: "ok", db: "ok", ...}` when this replica can serve; **503** `draining` while the SIGUSR1/SIGTERM drain is running, and 503 `degraded` when the database does not answer within the probe budget. This is the endpoint a balancer and `deploy.sh` poll. |
| `GET /metrics` | Prometheus metrics — **45 metric families** declared in `backend/app/obs.py` (runs/steps/tokens/errors, LLM latency and outcome by provider/model, pool saturation, in-flight runs, backlog depth, loop errors, MCP and listener state, spend, retention). The number of exported *series* is higher and varies, since most families are labelled. `text/plain; version=0.0.4`. |


### Fleet (M54)

| Endpoint | Description | Errors |
|---|---|---|
| `GET /replicas` | M54 (spec §18.9): the fleet as the database sees it — `{self, control_listener, dead_after_s, replicas: [{replica_id, started_at, heartbeat_at, subscribers, runs_in_flight, live}], budget}`. `budget` is the connection-budget arithmetic (`per_replica`, `pool`, `overflow`, `checkpointer`, `sessions`, `replicas`, `reserved`, `needed`, `declared_max`, `fits`, `max_replicas_at_declared`). A replica whose heartbeat is older than `dead_after_s` (45 s) is not `live`; its runs are failed by the survivors with `owner replica gone`. | — |
