# Concierge Agent — Tri-Layer Registry POC

## 1. Goal

Prove that a registry-driven, tri-layer agent architecture works end to end:

```
Orchestrator (planner + parallel dispatch)
  └─> Sub Agents  (persona + workflow DAG over skills)
        └─> Skills (minor persona + tool bindings)
              └─> Tools (ingested from MCP servers)
```

Every tier is backed by a registry with two write paths (static seed at startup, dynamic via admin UI) and one read path (the orchestrator reads registries only — it never distinguishes origin). Success criterion: plug an MCP server from the UI after startup, compose a skill from its tools, compose a sub agent from skills with a branching DAG workflow, and invoke it through chat with a visible run trace — without restarting the app.

Non-goals: authentication/authorization (assumed safe), multi-tenancy, production hardening, rate limiting, secrets management beyond env vars.

## 2. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, LangGraph, langchain-mcp-adapters, SQLAlchemy 2 + Alembic |
| LLM | **Provider-agnostic** via LangChain `init_chat_model`. Every model reference is a `provider:model` string (e.g. `anthropic:claude-sonnet-4-6`, `google_genai:gemini-2.5-pro`). POC default `anthropic:claude-sonnet-4-6`. Per-sub-agent model override field |
| DB | Postgres 16 (registries, run history, LangGraph checkpointer) |
| Frontend | React 19 + Vite + TypeScript + Tailwind (React ≥19 required by the official `@a2ui/react` answer-UI renderer). `@xyflow/react` (react-flow) for DAG preview. SSE for streaming |
| Runtime | docker-compose: `db`, `backend`, `frontend`. One command: `docker compose up`. **No message broker, no task queue, no Redis, no Celery** — runs execute as asyncio tasks inside the single FastAPI process; SSE is plain HTTP; HITL pause/resume rides the LangGraph Postgres checkpointer. Postgres is the only stateful infrastructure. |

### 2.1 Model provider abstraction (non-negotiable basic design)

A first-class provider layer in `backend/app/llm/` — used for **every** provider including Claude and Gemini, never bypassed. Rationale: a custom enterprise provider adapter (its own gateway, its own model list) will be added post-POC; it must plug in without touching any consumer code.

- **Port**: `class ModelProvider(Protocol)` — `provider_id: str`, `is_configured() -> bool`, `list_models() -> list[ModelInfo]`, `get_chat_model(model: str, params: ModelParams | None) -> BaseChatModel`. **`ModelParams` is normalized model configuration**: `{effort: 'none'|'low'|'medium'|'high', temperature, max_output_tokens}` — each adapter maps `effort` to its provider's knob (Anthropic thinking budget, OpenAI reasoning effort, Gemini thinking config); `ModelInfo` declares which params each model supports, and selecting an unsupported combination → 422 at save. The common currency across the whole codebase is LangChain's `BaseChatModel`: a provider adapter's only job is to return one. Everything downstream — LangGraph nodes, planner structured output, router, tools, `usage_metadata` token accounting — depends on `BaseChatModel`, never on a provider.
- **Provider registry**: adapters are code-registered at startup via `@model_provider` decorator scan (same pattern as `native/`), keyed by `provider_id`. Not UI-creatable (adapters are code); Settings lists them read-only with configured/unconfigured status.
- **Built-in adapters (POC)**: `anthropic`, `google_genai`, `openai` — thin wrappers delegating to LangChain `init_chat_model`/provider packages, each gated by its API key env var. A fourth slot is reserved by design for a custom gateway adapter later: implement the port, register, done — zero consumer changes.
- **Single entry point**: `get_model("provider:model") -> BaseChatModel` resolves the prefix against the registry and delegates to the adapter. Every LLM call in the system goes through it — planner, router, aggregator, skill nodes, direct-skill loops, native tools, native sub agents. No provider SDK or LangChain provider package imported anywhere outside `app/llm/`.
- **Model references**: always `provider:model` strings (settings, per-agent overrides, trace labels). Default `anthropic:claude-sonnet-4-6`. Selecting a model whose adapter reports unconfigured → 422 at save.
- **Neutrality rules**: structured outputs via LangChain's structured-output/tool-calling abstraction only; token accounting via `usage_metadata` only; prompts in `backend/app/prompts/` provider-neutral.
- **Adapter contract tests**: one shared pytest suite asserting the port contract (list/configure/get, **normalized `ModelParams` mapping incl. effort→provider knob**, tool-calling round-trip, structured output, usage metadata population against a fake); every registered adapter must pass it — this suite is what makes the future custom adapter safe to drop in.

Repo layout:

```
concierge-agent/
├── spec.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── api/          # routers per registry + chat + runs
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── mcp/          # MCP connection manager
│   │   ├── factory/      # worker factory (record -> compiled subgraph)
│   │   ├── llm/          # ModelProvider port, provider registry, adapters (§2.1)
│   │   ├── native/       # @native_tool / @native_skill / @native_sub_agent registrations
│   │   ├── orchestrator/ # planner + dispatch graph
│   │   └── seed/         # static seed data
│   └── tests/
└── frontend/
    └── src/
        ├── pages/        # Chat, McpServers, Tools, Skills, SubAgents, Runs, Settings
        └── components/
```

## 3. Data Model

Common columns on all registry tables: `id (uuid, immutable)`, `name`, `description`, `source ('static'|'dynamic')`, `status ('active'|'inactive'|'error')`, `created_at`, `updated_at`, `deleted_at (soft delete)`. Each tier additionally carries a `kind` discriminator (defined per tier below); `source` + `kind` + tier are attached to every trace span and log line (§10).

### 3.1 mcp_servers
- `transport`: `'stdio' | 'http'`
- stdio: `command`, `args (jsonb)`, `env (jsonb)`
- http: `url`, `headers (jsonb)`
- `last_connected_at`, `last_error`

### 3.2 tools
- `kind`: `'mcp' | 'native'`
- `mcp_server_id` (FK, required when `kind='mcp'`, null when `kind='native'`)
- `tool_name` (name as exposed by the MCP server, or the native provider registration name)
- `native_ref` (text, nullable) — for `kind='native'`: dotted path of the registered provider entry (e.g. `native_tools.summarize_graph`)
- `tool_key` (string, unique) — human-facing identifier. Defaults to `{server_name}.{tool_name}` for MCP tools (collision-safe across servers exposing the same tool name) and the registration name for native tools; auto-generated uuid string only if neither yields a unique key. **Editable later.** Internal references (skill_tools join) always use the immutable `id`, so renaming `tool_key` never breaks bindings.
- `direct_exposure (bool, default false)` — when true, the orchestrator may call this tool itself, without a sub agent. Note: direct tool calls carry no skill persona — the tool runs under the orchestrator's own prompt.
- `input_schema (jsonb)` — JSON Schema from `tools/list` (mcp) or derived from the callable/subgraph input schema (native)

### 3.3 skills
- `kind`: `'native' | 'custom'` — **native skills are markdown files** (`backend/app/native/skills/*.skill.md`, YAML frontmatter + body) scanned into the registry at startup; **custom skills are the same document shape** authored in the UI and stored in the registry. One format, two homes.
- **Skill document** = frontmatter (`name`, `description`, `persona`, `tools: [tool_keys]`, `direct_exposure`) + markdown body (`instructions`).
- `instructions (text, markdown)` — the body: free-form, typically a multi-step process. **Soft workflow**: steps guide the LLM inside a single tool-loop node and are not machine-enforced (the hard, machine-executed workflow is the sub agent DAG, §3.5). A step need not tie to any tool — pure reasoning/formatting steps are valid. Steps may reference bound tools inline via `{tool:server.tool_name}` mentions; save validates every mention resolves to a bound tool.
- `model (text, nullable)` + `model_params (jsonb, nullable)` — optional per-skill override (`provider:model` + normalized params, §2.1): a heavy research skill can run a stronger model at high effort while a formatting skill runs a cheap one. Null inherits from the invoking sub agent, then defaults.
- `persona (text)` — the "minor persona": short instruction block injected when this skill's node runs
- `skill_tools` join table: `skill_id`, `tool_id`. **Binding = availability, strictly**: the skill's loop receives exactly its bound tools and nothing else — no ambient tools, no cross-skill visibility, in every execution context including orchestrator fallback (§7.0). A tool can belong to many skills; a skill can tag many tools, including system-seeded static ones.
- `direct_exposure (bool, default false)` — when true, the orchestrator may execute this skill inline (skill persona + instructions + bound tools injected into an orchestrator tool-loop step) without spinning a sub agent.
- **Strict id references**: every request that binds or invokes a skill (workflow nodes, skill endpoints) must carry an explicit `skill_id`; no name-based resolution. Missing/unknown `skill_id` → 422 rejected.

### 3.4 sub_agents
- `kind`: `'native' | 'custom'`
  - **native**: a hand-written compiled LangGraph graph registered at startup (`@native_sub_agent(name, description, covers_skill_ids=[])` scan). `covers_skill_ids` declares which registry skills this agent can service — used by capability resolution (§7). Registry stores its card (name, description, `native_ref`); the worker factory is bypassed — invocation calls the registered graph directly. Must accept the standard state schema (`{messages, task, node_outputs}`) and use the shared Postgres checkpointer; HITL/interrupts are permitted (native sub agents run top-level, not tool-wrapped). `workflow` is null.
  - **custom**: registry-composed — persona + workflow DAG over skills (the worker-factory path). The DAG is the **hard**, machine-executed workflow across skills; multi-step processes inside a skill's `instructions` are soft guidance within one node (§3.3). Custom sub agents are built from the skills pool; each skill in the picker surfaces its bound tools so the full skills-vs-tools pool is visible at composition time.
- `persona (text)` — top-level persona for the worker (custom only)
- `model (text, nullable)` + `model_params (jsonb, nullable)` — `provider:model` string + normalized params (§2.1) override; null falls back to `default_model` / `default_model_params` settings. **Resolution order for any skill node: skill override → sub agent override → settings defaults.**
- `workflow (jsonb)` — DAG, schema below (custom only)
- `sub_agent_skills` join table derived from workflow at save time (for badge queries)

### 3.5 Workflow DAG schema (jsonb)

```json
{
  "nodes": [
    {"id": "n1", "type": "skill", "skill_id": "<uuid>", "instructions": "optional per-node addendum"},
    {"id": "n2", "type": "hitl",  "prompt": "Approve sending the summary?"},
    {"id": "n3", "type": "skill", "skill_id": "<uuid>"}
  ],
  "edges": [
    {"from": "START", "to": "n1"},
    {"from": "n1", "to": "n2", "condition": "if research found results"},
    {"from": "n1", "to": "END", "condition": "if nothing found"},
    {"from": "n2", "to": "n3"},
    {"from": "n3", "to": "END"}
  ]
}
```

Rules:
- Node types: `skill`, `hitl`. `skill` nodes reference a skill registry record. `hitl` nodes pause the run and wait for chat approval.
- Branching: multiple outgoing edges from one node with `condition` strings. Conditions are natural-language; a router step (LLM call with the node's output + condition list) selects the edge. Unconditional single edge = direct transition.
- **Error edges**: an edge may carry `"on": "success" | "error"` (default `success`). When a node fails (tool/MCP error, LLM error), execution routes via its `error` edge if one exists — the failed node's error text lands in state for the downstream node. No error edge → node failure fails the run (step + run marked `failed`, error surfaced in chat). Router/condition evaluation applies only to `success` edges.
- Parallelism: multiple unconditional outgoing edges from one node fan out (LangGraph `Send`); a node with multiple incoming edges joins **when all *reachable* incoming edges have completed** — branches not taken (unselected conditions, error paths bypassed) are marked unreachable at route time so joins never deadlock.
- Validation at save (reject, don't warn): exactly one `START`, at least one path to `END`, no cycles, all `skill_id`s resolve to active skills, all node ids unique, edges reference existing nodes, at most one `error` edge per node.

### 3.6 conversations / runs / run_steps
- `conversations`: `id`, `title (auto from first message)`, `created_at`, `updated_at`. Chat is multi-turn: every run belongs to a conversation, and the planner receives the **full conversation history** (all prior user messages + final answers in the conversation) as context.
- `runs`: `id`, `conversation_id (FK)`, `chat_message`, `plan (jsonb)` (planner output), `snapshot (jsonb)` — resolved config frozen at dispatch: for each capability used, the persona/workflow/model/tool definitions as they were at run time, so later registry edits never rewrite trace history, `answer_ui (jsonb, nullable)` — optional model-generated declarative answer UI (§7.1 `answer_ui` event; persisted so conversation reload and the Runs page re-render it), `status ('running'|'paused_hitl'|'completed'|'failed'|'cancelled')`, `started_at`, `finished_at`, `total_input_tokens`, `total_output_tokens`
- `run_steps`: `id`, `run_id`, `parent_step_id (nullable — nested steps, e.g. inside a native subgraph tool)`, `sub_agent_id`, `node_id`, `step_type ('plan'|'route'|'skill'|'hitl'|'tool_call'|'aggregate')`, `input (jsonb)`, `output (jsonb)`, `model`, `input_tokens`, `output_tokens`, `started_at`, `finished_at`, `error`

### 3.7 app_settings

Key-value store (`key`, `value jsonb`, `updated_at`) read live at runtime — changes apply to the next run, no restart. Keys: `orchestrator_mode ('graph'|'agentic')`, `orchestrator_full_fallback_enabled (default true)`, `default_model`, `default_model_params`, `planner_model`, `planner_model_params`, `aggregator_model`, `aggregator_model_params`, `max_parallel_dispatch`, `max_plan_steps`, `max_tool_iterations` (per skill-node tool loop; exceeded → node fails, error-edge semantics apply), `dynamic_worker_fallback_enabled`, `direct_exposure_cap_warning`, `answer_ui_enabled (default true)`, `mcp_health_interval_s`, `log_level`, `langsmith_enabled`, `langsmith_endpoint`, `langsmith_project`, `otlp_endpoint`. Anthropic API key stays env-only — never stored in DB or shown in UI, even in a POC.

## 4. Registry API

REST, JSON, `/api/v1`. All list endpoints support `?include_deleted=false&source=&q=`.

| Resource | Endpoints |
|---|---|
| MCP servers | `GET/POST /mcp-servers`, `GET/PATCH/DELETE /mcp-servers/{id}`, `POST /mcp-servers/{id}/reconnect`, `POST /mcp-servers/{id}/refresh-tools` |
| Tools | `GET /tools`, `GET/PATCH /tools/{id}` (PATCH: description/status only — schema is server-owned), `GET /tools/{id}/skills` (reverse lookup for badges) |
| Skills | `GET/POST /skills`, `GET/PATCH/DELETE /skills/{id}`, `GET /skills/{id}/sub-agents`, `POST /skills/check-overlap` (pre-save judge, below) |
| Sub agents | `GET/POST /sub-agents`, `GET/PATCH/DELETE /sub-agents/{id}`, `POST /sub-agents/{id}/validate` (dry-run factory compile), `POST /sub-agents/check-overlap` (pre-save judge, below) |
| Chat | `GET/POST /conversations`, `GET /conversations/{id}` (messages + runs), `POST /chat` (`{conversation_id, message}` → `run_id`), `GET /chat/stream/{run_id}` (SSE), `POST /runs/{run_id}/hitl` (`{"decision": "approve"|"deny", "note": "..."}`) |
| Runs | `GET /runs`, `GET /runs/{id}` (includes ordered steps), `POST /runs/{id}/cancel`, `POST /runs/{id}/retry` (re-plan from original message), `DELETE /runs/{id}` |
| Settings | `GET /settings`, `PATCH /settings` (partial key updates), `GET /hitl/pending` (all paused runs), `POST /seed/reload` (idempotent re-seed) |

Cross-cutting rules:
- `source=static` records: content PATCH/DELETE return 403 with reason; the single exception is `status` (and `direct_exposure` where applicable), which is togglable on static records — the command center can switch anything off without editing its definition. Rendered read-only-with-toggles in UI.
- Referential integrity enforced at save time: deleting a skill referenced by an active sub agent → 409 listing dependents. Same for tools in skills and MCP servers with tools in skills.
- Every mutating endpoint bumps `updated_at`; registry reads are always live from DB (no caching layer in POC).

**Overlap guard (LLM-as-judge, advisory).** Before a skill or sub agent is created or updated, the UI calls the matching `check-overlap` endpoint with the draft (`exclude_id` set on updates so a record never matches itself). The judge — an LLM call through the standard provider port, prompt in `app/prompts/overlap_judge.md`, structured `OverlapVerdict` output — compares the draft by purpose against existing records: skills against active skills **and tools**, sub agents against active sub agents **and skills**. At ≥70% overlap the response flags it with the match (type/id/name) and reasoning, and the UI shows a confirm dialog: **save anyway** or **cancel and use the existing match**. The check is advisory only: the save endpoints stay unguarded, and judge failure (no key, provider error) fails open with `overlap: false` plus a reasoning note — infrastructure trouble must never block registry writes. Tools are deliberately exempt: MCP ingest is dynamic, and two servers legitimately exposing similar tools is not an error.

## 5. MCP Connection Manager

Singleton service owning one client session per active `mcp_server` record.

- **Register (dynamic)**: POST creates record → manager connects (stdio: spawn `command args` inside backend container; http: streamable-HTTP client) → `tools/list` → upsert `tools` rows (`source` inherited from server record) → status `active`. Connection failure → status `error`, `last_error` set, record kept for retry.
- **listChanged**: subscribe to tool-list-changed notifications; on receipt re-run `tools/list` and reconcile (add new, mark removed tools `inactive`).
- **Health**: ping loop every 30s; failures flip status to `error`; `reconnect` endpoint retries.
- **Startup**: manager loads all non-deleted `mcp_servers` (static seed + previously added dynamic ones) and connects each. Dynamic records therefore survive restarts — DB is the source of truth, not memory.
- **Invocation**: skills resolve tool bindings → manager exposes each bound tool as a LangChain tool object (via langchain-mcp-adapters) for the worker factory.

## 5b. Native Tool Provider

Native tools are code-defined tools that live in the backend — plain Python callables or **compiled LangGraph subgraphs exposed as tools** (`graph.as_tool()` / a wrapper invoking the subgraph). They register into the same `tools` registry (`kind='native'`) and are bindable to skills exactly like MCP tools.

- **Registration**: at startup, the provider scans `backend/app/native/` for entries decorated with `@native_tool(name, description)` (and `@native_sub_agent`, §3.4); native skills load from `native/skills/*.skill.md` (§3.3). Each entry is upserted into `tools` (`kind='native'`, `source='static'`, `native_ref` = dotted path, `input_schema` derived from the callable signature / subgraph state schema). Entries removed from code are marked `inactive` on next startup.
- **No dynamic native tools**: native tools cannot be created from the admin UI — that would mean accepting executable code at runtime. UI shows them with a `native` badge; description/status editable, nothing else.
- **Invocation**: worker factory resolves tool bindings by `kind` — `mcp` via the MCP manager, `native` via the provider's in-process callable. Same LangChain tool interface either way; skills and sub agents are agnostic.
- **Guardrails (validated at startup registration and at skill/sub-agent save)**:
  1. **No HITL inside native subgraphs** — LangGraph interrupts do not propagate cleanly out of a tool call; a native subgraph containing `interrupt()` is rejected at registration.
  2. **No registry sub agent wrapping** — a native tool may not invoke a registry sub agent (prevents cycles: sub agent → skill → tool → same sub agent). Native subgraphs are self-contained; composition across registry sub agents belongs to the orchestrator planner, not the tool layer.
  3. **Token + trace capture** — native subgraph invocations report LLM usage via callback; recorded as a `tool_call` step with nested child steps (`run_steps.parent_step_id`) so trace and token rollups stay accurate.
- **Seed**: one static native tool, `summarize-and-structure` (single-node subgraph: LLM call that converts raw text into a structured JSON summary), bound into the `web-research` skill — proves the subgraph-as-tool path end to end alongside MCP tools in the same skill.

## 6. Worker Factory

`build_worker(sub_agent_record) -> CompiledStateGraph`. The load-bearing component.

- **Compilation**: workflow DAG → hand-built LangGraph `StateGraph`. **Each `skill` node is implemented with LangChain's `create_agent`** (the standard tool-loop constructor): model from `get_model()`, tools from the skill's bindings, system prompt from the assembly order below, loop bounded by `max_tool_iterations`. **The DAG shell is never `create_agent`** — routing, conditional/error edges, `Send` fan-out, joins, and `interrupt()` are explicit StateGraph construction, because that's the deterministic envelope. `skill` node → agent node: system prompt assembled in order (1) sub agent persona, (2) skill persona, (3) skill `instructions` (markdown body), (4) node `instructions` addendum from the DAG, (5) tool-usage guidance; tools = the skill's bound tools resolved by kind (`mcp` → MCP manager, `native` → native tool provider). `hitl` node → LangGraph `interrupt()` carrying the node's `prompt`. Conditional edges → router function (LLM call: node output + condition strings → chosen edge). Fan-out edges → `Send`; joins via reducer state.
- **State**: `{messages, node_outputs: dict[node_id, output], task}`. Each skill node appends its output; downstream nodes receive prior outputs in context. **M3 constraint**: state reducers must be order-insensitive — parallel branches complete in nondeterministic order, and joins must converge to the same state regardless of interleaving (keyed dict merges, no order-dependent appends).
- **Checkpointing**: Postgres checkpointer keyed by `run_id` — required for HITL pause/resume.
- **Compile-time = save-time**: `POST /sub-agents/{id}/validate` runs full compilation without invocation; save rejects records that fail compile. The orchestrator never selects a broken worker.
- **Caching**: compiled graphs cached in-process keyed by `(sub_agent_id, updated_at)`; a registry update naturally invalidates via the changed timestamp.

## 7. Orchestrator

Two selectable orchestrator modes share every subsystem (registries, ladder policy, factory, MCP manager, provider layer, tracing); `app_settings.orchestrator_mode: 'graph' | 'agentic'` (default `graph`) switches per run.

### 7.0 Middleware layer (the sync backbone, both modes)

Three custom middlewares wrap the registries and are the **only** path by which capabilities reach any `create_agent` instance in the system:

- **ToolsRegistryMiddleware** — dynamic-tools hook: resolves tool objects live from the tool registry (via MCP manager / native provider) at each model call. A reconnected MCP server or newly ingested tool is visible on the next loop iteration, no rebuild.
- **SkillsRegistryMiddleware** — injects exposed skills: summaries into the system prompt (dynamic prompt hook) and each exposed skill as a callable capability whose handler runs the inline skill loop.
- **SubAgentsRegistryMiddleware** — deepagents-style: exposes dispatch as tools built live from sub agent cards; the handler is the resolution-ladder executor (validate → snapshot → invoke compiled graph on the shared checkpointer). `interrupt()` raised inside the dispatched graph propagates to the parent for HITL; **dispatch handlers are idempotent** because resume replays the tool call.
- Standard middlewares on every `create_agent` instance (skill nodes, rung-1 loops, agentic orchestrator): **SummarizationMiddleware** (context compaction — also applied to conversation-history assembly, closing the long-conversation gap) and the built-in call-limit middlewares implementing `max_tool_iterations` instead of custom counting.

**Middleware policy**: prefer out-of-box LangChain middleware configured via its options; compose or subclass an existing hook when that suffices; write custom middleware only when nothing out-of-box can be configured to fit (the three registry middlewares qualify — nothing OOB projects a Postgres registry). Never duplicate an OOB middleware's concern.

**Composition (one helper, `build_middleware_stack(context)`, used everywhere)**:
- **Skill loops** (nodes in custom sub agents, rung-1 inline, ephemeral workers, skills invoked from fallback): SummarizationMiddleware + call-limit middlewares + ToolsRegistryMiddleware in **scoped mode** — resolves live tool objects for the skill's bound ids only. Never SkillsRegistry or SubAgentsRegistry middleware here: a skill cannot see other skills, agents, or unbound tools (§3.3 invariant enforced structurally).
- **Agentic orchestrator**: all three registry middlewares (exposure-gated; full-catalog in fallback) + TodoListMiddleware + SummarizationMiddleware + limits.
- **Graph orchestrator**: no middleware on the shell (it isn't `create_agent`); its rung-1 loops and fallback loop use the stacks above.
- **Native sub agents**: contract requires only state schema + checkpointer; authors using `create_agent` internally may attach the shared stacks via the same helper.
Registry middlewares are stateless projections over Postgres (fresh read per model call), so instances are cheap and share nothing — reuse is by class + config, never by shared state.

**Sync invariant**: registries are the single source of truth; nothing caches them except compiled graphs (keyed by `updated_at`, self-invalidating). Visibility of a new MCP server, tool, skill, or sub agent: next model call in any middleware-backed loop, next run for graph-mode plan context. No manual refresh anywhere.

**Self-service fallback (full catalog)**: when semantic routing fails — the planner cannot produce a confident capability match, or every plan entry fails resolution — and `orchestrator_full_fallback_enabled` is true, the orchestrator handles the query itself instead of spinning a worker: a `create_agent` loop whose registry middlewares switch to **full-catalog mode** — ALL active tools and ALL active skills become callable, exposure flags ignored. This is the deliberate backup for bad descriptions: routing needs good prose, the fallback doesn't. Two invariants hold even here: a skill invoked from fallback still runs with only its bound tools (isolation is never suspended), and every fallback capability use is traced with route rung `fallback`. In agentic mode the orchestrator's base capabilities stay exposure-gated; a `use_full_catalog` escalation tool unlocks full-catalog mode mid-loop, logged as the same fallback route. Full catalog in context is the token cost we normally avoid via progressive disclosure — acceptable precisely because this path only runs when disclosure-based routing has already failed.

### 7.1 Graph mode (default)

A hand-built LangGraph `StateGraph` — **not** `create_agent`: `plan → resolve → dispatch (parallel) → aggregate`. The planner is a structured-output call, resolution is pure code, dispatch is graph mechanics — none of that is a tool loop. `create_agent` appears in the orchestrator only inside rung-1 direct-skill execution, where the inline skill loop is itself a `create_agent` instance (persona + instructions + bound tools).

- **Plan**: progressive disclosure — prompt contains compact registry summaries only: sub agent cards (name + description + skill names) plus, listed separately as directly usable capabilities, all `direct_exposure=true` tools and skills. Planner LLM outputs JSON: `[{capability: {type: 'direct_tool'|'direct_skill'|'sub_agent'|'spin_worker', id|skill_ids}, task, depends_on: []}]`.
- **Capability resolution ladder** — for each capability the plan needs, in order:
  1. **Direct**: the tool/skill has `direct_exposure=true` → orchestrator executes it itself (direct tool = plain tool call; direct skill = inline tool-loop step with the skill persona).
  2. **Native sub agent**: a registered native agent whose `covers_skill_ids` includes the needed skill → dispatch to it.
  3. **Custom sub agent**: a custom agent whose workflow includes the skill (via `sub_agent_skills`) → dispatch to it.
  4. **Ephemeral dynamic worker**: none of the above → the worker factory builds a worker on the fly over one **or several** skills (`skill_ids[]`, executed as a sequential chain in the given order; first skill's persona leads, later personas append per node). Not persisted to any registry; traced with sub-agent-tier `kind='dynamic'`, `entity_id=null`, skill ids recorded on the steps. Discarded after the run.
  The ladder is deterministic and logged as a `route` step, so every run trace shows why a capability resolved the way it did.
- **Plan validation + repair**: the planner's JSON is schema-validated and every referenced id checked against the registries. Invalid output → one repair retry (same prompt + the validation errors). Still invalid → run fails with a clear chat message; the raw planner outputs are stored on the run for debugging.
- **Cancellation**: `POST /runs/{id}/cancel` is cooperative — the run task is cancelled at the next step boundary, in-flight steps marked `cancelled`, run status `cancelled`, checkpoint retained for inspection. Cancel on a `paused_hitl` run resolves it as cancelled.
- **SSE event contract** (`GET /chat/stream/{run_id}`), every event `{type, run_id, ts, payload}`:
  `plan {entries[]}` · `route {capability, rung, resolved_to}` · `dispatch_start|dispatch_end {step_id, tier, kind, entity_id}` · `token {text}` (aggregator stream) · `answer_ui {a2ui: messages[]}` (optional declarative answer UI as A2UI v0.9 protocol messages, after the token stream, before `done`) · `hitl_request {step_id, prompt}` · `run_status {status}` · `error {step_id?, message}` · `done {answer, tokens}`.
- **Dispatch**: entries with no unmet `depends_on` dispatch in parallel (`Send`); dependents wait on outputs. Each plan entry executes via its resolved capability — direct tool call, inline skill loop, registered native/custom sub agent, or factory-built ephemeral worker. Every step is recorded to `run_steps`.

### 7.2 Agentic mode

The orchestrator is a single `create_agent` with a finetuned system prompt (concierge instructions: when to answer directly, when to use capabilities, how to sequence) and the full middleware stack: TodoListMiddleware (visible planning/self-correction), SummarizationMiddleware, and the three registry middlewares — so its capabilities at every model call are exactly the live registries: exposed tools, exposed skills, sub agent dispatch tools, plus a `spin_worker(skill_ids, task)` tool for the rung-4 fallback. Properties relative to graph mode: planning is emergent (todos, not a validated plan artifact); parallelism only via parallel tool calls in one turn; the ladder becomes tool-construction policy inside the middlewares, with each capability invocation still logged as a `route`-equivalent step via the tool-call wrapper; HITL propagates through interrupt-in-tool with idempotent-replay dispatch. Same SSE contract (`plan` events carry the todo list), same run/step recording, same labels — traces from both modes are directly comparable, which is the point: the POC can A/B explicit-planner vs agentic orchestration on identical registries.
- **HITL propagation**: a worker interrupt pauses the run (`status=paused_hitl`), emits an SSE `hitl_request` event with the prompt; `POST /runs/{id}/hitl` resumes from checkpoint (`approve` continues, `deny` routes that node to END with a denial note in state).
- **Aggregate**: final LLM call merges worker outputs into one chat answer; token totals rolled up onto the run.
- **Declarative answer UI (A2UI, model-generated)**: when `answer_ui_enabled`, a follow-up structured-output call (same aggregator model, through the §2.1 port — provider-agnostic by construction) generates a compact component tree (whitelisted types: `card`, `text` (markdown), `stat`, `table`, `list`, `badge`, `divider`, `link`, `sources`), which a **deterministic server-side translator converts into A2UI v0.9 protocol messages** (`createSurface` + `updateComponents`, literal values, basic catalog). The model contributes content; our code guarantees protocol-valid A2UI on the wire. Emitted as the `answer_ui` SSE event (`{a2ui: messages[]}`) and persisted on `runs.answer_ui`. **Failure-safe**: schema-invalid or failed generation is dropped silently — the streamed text answer is always the source of truth; the UI payload only ever augments it. Applies to both orchestrator modes.
- **Fallback**: the planner may return an empty plan with a direct answer for trivial requests needing no capability. When it instead reports no confident match for a capability-needing query, the self-service full-catalog fallback (§7.0) takes over rather than answering blind or force-spinning a worker.

## 8. Admin UI

Single React app, left nav: **Chat, MCP Servers, Tools, Skills, Sub Agents, Runs, Settings**. Consistent table pattern everywhere: search, source filter, **kind filter**, `static`/`dynamic` badge, **kind badge** (`mcp`/`native`/`custom`), status pill, row click → detail/edit drawer. Static records: definition fields disabled + "static" notice, but status/exposure toggles remain live.

### 8.1 MCP Servers
- Table: name, transport, status pill (active/error + last_error tooltip), tool count, last connected.
- Register form: transport toggle → stdio fields (command, args, env key-values) or http fields (url, headers). **Env and header values render masked with reveal-on-click** — the POC stores them, the UI doesn't display them by default. Test-connection button (dry connect + tool count preview) before save.
- Row actions: reconnect, refresh tools, edit, soft delete (blocked with dependents dialog if its tools are bound to skills).

### 8.2 Tools
- Table: tool name, server, description, **skill badges** — one chip per skill that binds this tool, click chip → that skill's detail. Zero chips renders "unassigned" chip. **`direct` badge** when `direct_exposure=true`.
- Detail drawer: input schema (pretty JSON), server link, editable description/status, **"Expose to orchestrator" toggle**.

### 8.3 Skills
- Table: name, persona preview (first line), **tool badges** (chips → tool detail), **sub agent badges** (chips per sub agent whose workflow uses this skill), source, status.
- Create/edit: **template-based skill document editor** — frontmatter as form fields (name, description, persona, "Expose to orchestrator" toggle, **optional model + effort override** (model select filtered to supported params, effort: none/low/medium/high, temperature), **tool tags**: searchable multi-select across the tool registry, grouped with system-seeded static tools first, source/kind badges on each) + markdown body editor pre-loaded with the skill template (Purpose / Steps / Output format sections); `{tool:...}` mentions autocomplete from tagged tools only and validate at save; side-by-side rendered preview. Save validates all tagged tool ids active + every mention resolves to a tagged tool. Save first runs the §4 overlap guard: at ≥70% match a dialog shows the match + judge reasoning with **Save anyway** / **Cancel (use the existing one)**.

### 8.4 Sub Agents
- Table: name, persona preview, model (or "default"), **skill badges**, run count, source, status.
- Create/edit: name, description, persona, **model + effort override selects** (model override select, effort none/low/medium/high, temperature — filtered to the model's supported params), **workflow builder** — form-based, opened from a **starter template** picker (Blank · Sequential pipeline · Branch + HITL approve · Parallel fan-out/join: pre-filled DAG skeletons with placeholder nodes the user fills via skill picker): node list (add skill node via skill picker / add HITL node with prompt), edge list (from → to + optional condition text + on: success/error), with a live read-only react-flow graph preview rendering nodes, edges, condition labels, and validation errors inline. Save runs `/validate`; compile errors shown next to the offending node/edge. Save also runs the §4 overlap guard: at ≥70% match a dialog shows the match + judge reasoning with **Save anyway** / **Cancel (use the existing one)**.
- **Native sub agents** render as a definition card — description, `covers_skill_ids` chips, `native_ref` — with no DAG builder (there is no workflow record; the graph is code). Read-only except status.
- Row action: "Test invoke" — opens Chat pre-targeted at this sub agent (bypasses planner).

### 8.5 Chat
- Conversation sidebar (list + new conversation); selecting one loads its history. Streaming conversation (SSE): assistant tokens, plus inline system cards for plan (**graph mode**: sub agents + parallel groups; **agentic mode**: the live todo list, items checking off as the loop progresses), each dispatch start/finish, and **HITL cards** with the prompt + Approve/Deny buttons and optional note. **Self-service fallback engagement renders a distinct banner** ("full-catalog fallback — descriptions didn't route this") linking to its route step. Each response footer links to its run trace.
- **Declarative answer UI renderer**: `answer_ui` payloads are A2UI v0.9 messages rendered beneath the text answer with the official **`@a2ui/react` + `@a2ui/web_core`** renderer (`A2uiSurface` + `MessageProcessor`, basic catalog) — payloads are data, not markup (no HTML/JS injection surface). Re-rendered from `runs.answer_ui` when a conversation reloads.

### 8.6 Runs
- Table: time, message excerpt, status, **orchestrator mode badge**, sub agents involved, duration, tokens.
- Detail: plan JSON, ordered step timeline grouped by sub agent (node id, type, model, tokens, duration, expandable input/output, tool calls with args/results), errors highlighted. Paused runs show pending HITL with resolve buttons. Row/detail actions: **cancel** (running), **retry** (failed — re-plans from the original message), **delete**.

### 8.7 Settings (command center)

- **Models**: default, planner, aggregator — each a `provider:model` select **plus params (effort none/low/medium/high, temperature, max output tokens), options filtered to what the selected model supports** — applied to next run, no restart. **Providers panel**: read-only list of registered provider adapters with configured/unconfigured status and their model lists (§2.1).
- **Orchestrator**: **mode toggle (graph | agentic, §7)**, **full-catalog fallback on/off**, **declarative answer UI on/off**, max parallel dispatch, max plan steps, dynamic-worker fallback on/off, direct-exposure cap warning threshold — when current exposures exceed the threshold, the Tools and Skills pages show a context-cost warning banner.
- **MCP**: health-check interval; global reconnect-all and refresh-all-tools buttons.
- **Observability**: log level select, LangSmith toggle, OTLP endpoint field.
- **HITL queue**: all currently paused runs across chats, resolvable inline.
- **Data**: seed-reload button (idempotent), run-history purge with confirm.
- Every control maps to `app_settings` or an existing endpoint — nothing on this page requires a container restart; API key is deliberately absent (env-only).

## 9. Seed Data (static)

Loaded idempotently at startup, all `source=static`:

1. **MCP servers**: `fetch` (`uvx mcp-server-fetch`, stdio) and `filesystem` (`npx -y @modelcontextprotocol/server-filesystem /workspace`, stdio, sandboxed to a `/workspace` volume).
2. **Skills** (native `.skill.md` files in `app/native/skills/`): `web-research` (persona: careful researcher, cite sources; tools: fetch; instructions: multi-step research process where the final synthesis step ties no tool) and `file-ops` (persona: precise file clerk, confirm paths; tools: read/write/list from filesystem server).
3. **Sub agent**: `research-concierge` — persona: helpful research concierge; workflow: `START → research(web-research) →[found results]→ hitl("Save findings to a file?") → write(file-ops) → END`, with `research →[nothing found]→ END` branch. Exercises DAG branching + HITL + both skills in one seed.
4. **Native tool**: `summarize-and-structure` (§5b), bound into `web-research` — proves mixed mcp+native tools in one skill.

## 10. Observability

Every span and log line carries the label set: `{run_id, step_id, tier ('tool'|'skill'|'sub_agent'|'orchestrator'), kind, source, entity_id, entity_name, model, effort, input_tokens, output_tokens, duration_ms, status}`. Sub-agent-tier `kind` values: `native | custom | dynamic` (ephemeral workers).

- **Structured logs**: structlog, JSON to stdout — directly shippable to ELK/Filebeat without parsing config. One log event per registry mutation, MCP lifecycle event, run step start/finish, and error.
- **Traces**: OpenTelemetry instrumentation over the orchestrator graph, worker invocations, tool calls (nested spans mirror `run_steps.parent_step_id`). OTLP exporter, endpoint via env — points at Grafana Tempo/Jaeger/anything OTLP.
- **LangSmith**: full framework-level traces (prompts, completions, tool calls) for every LLM touchpoint — both orchestrator modes, all `create_agent` loops, dispatched sub agent graphs, fallback loops. **Local or remote by endpoint**: `langsmith_endpoint` (self-hosted instance or SaaS) + `langsmith_project` + `langsmith_enabled` live in `app_settings`; the tracer is constructed **per run** from settings and injected via callbacks — not process env — so enabling/pointing LangSmith requires no restart. `LANGSMITH_API_KEY` alone stays env-only. Runs simultaneously with OTel; `run_id` is attached as LangSmith metadata so PG traces, OTel spans, and LangSmith runs cross-reference. This is the connectivity the §15 eval feature reuses (datasets + experiment results via the same client config).
- **Metrics**: Prometheus `/metrics` — counters (runs, steps, tool calls, errors) and histograms (run duration, step duration, tokens), all labeled with `tier/kind/source` — Grafana dashboards slice native vs custom vs mcp directly.
- **Correlation**: `run_id` present in logs, spans, and metrics exemplars; UI run trace links are the same id.

## 11. Testing

- **Backend unit** (pytest): skill document parsing (frontmatter + body, `.skill.md` startup scan, `{tool:...}` mention validation incl. mention of an untagged tool rejected), worker factory (DAG → graph compile: sequential, branch, parallel, error edges, reachable-join semantics, HITL, multi-skill ephemeral build, invalid DAG rejection matrix), persona merge order, planner validation + repair loop, registry validation rules (referential integrity, static write rejection), MCP manager against a stub MCP server (connect, ingest, listChanged reconcile, error status), native tool provider (registration scan, schema derivation, HITL-in-subgraph rejection, sub-agent-wrap rejection, mixed mcp+native skill invocation, nested trace + token rollup).
- **API contract** (pytest + httpx): CRUD per registry, cross-reference endpoints, 403 static, 409 dependents, chat → run → HITL resume happy path with mocked LLM, capability resolution ladder (direct tool, direct skill, native match via covers_skill_ids, custom match, ephemeral dynamic worker fallback — one test per rung, plus precedence when multiple rungs match), registry middlewares (live tool appearance mid-loop, skill/sub-agent tool construction from registry state, idempotent dispatch replay, **strict tool isolation — a skill loop can never see unbound tools, including in fallback**, full-catalog fallback triggering on no-confident-match), both orchestrator modes over the same fixture registries.
- **UI** (Playwright): register stdio MCP server → tools appear → create skill → badges correct on both Tools and Skills pages → build sub agent with branch + HITL, validation error then fix → chat invoke → approve HITL card → run trace shows all steps. Static record toggle-only rendering. Settings page: model change reflected in next run's trace labels, run cancel/retry.
- LLM calls mocked/recorded in all tests via a LangChain fake chat model injected through the §2.1 factory — tests never touch a provider SDK. One optional live smoke test behind an env flag, parameterized over every provider with a configured key (proves provider-agnosticism on real APIs).

## 12. Milestones

| # | Deliverable | Proves |
|---|---|---|
| M1 | Postgres schema + registry API + seed + static rejection rules | Registries as single source of truth |
| M2 | MCP manager: stdio + http connect, ingest, listChanged, health | Dynamic tool tier |
| M3 | Worker factory + validate endpoint (sequential, branch, parallel, HITL compile) | Dynamic sub agent tier |
| M4 | Orchestrator both modes (graph + agentic) + middleware layer (§7.0) + chat SSE + HITL resume + run recording + observability (structlog JSON, OTel spans, /metrics) | End-to-end invocation, traceable, mode-comparable |
| M5 | Admin UI: all seven pages incl. Settings command center, badges, workflow builder, trace view, run controls | Full admin manageability — every runtime control in UI |
| M6 | Test suites green + docker-compose polish + README | Done |

Each milestone lands with its tests. M1–M4 are API-verifiable via curl before M5 exists.

## 13. Environment & Conventions

Env vars (all in `.env.example`, committed — no secrets in it): `ANTHROPIC_API_KEY` (required for the default provider, never in DB/UI), `GOOGLE_API_KEY` / `OPENAI_API_KEY` (optional — presence enables that provider in Settings model selects, spec §2.1), `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` (compose db init), `DATABASE_URL`, `LANGSMITH_API_KEY` (key only — enable/endpoint/project are runtime settings, §10), `OTEL_EXPORTER_OTLP_ENDPOINT` (bootstrap default; the `otlp_endpoint` setting overrides at runtime), `WORKSPACE_DIR` (filesystem MCP sandbox), `BACKEND_PORT`, `FRONTEND_PORT`, `VITE_API_BASE_URL` (frontend → backend, build-time).

Conventions: Python — ruff (lint+format), mypy strict on `app/`, pytest, async SQLAlchemy, Pydantic v2 schemas separate from ORM models. TypeScript — eslint + prettier, strict tsconfig, TanStack Query for API state, no Redux. Conventional commits. Alembic migration per schema change. All LLM prompts live in `backend/app/prompts/` as versioned files, not inline strings.

## 14. Acceptance Demo Script (definition of done)

Runs top to bottom on a fresh `docker compose up`, no restarts:

1. Open admin → seed visible: 2 MCP servers, tools with `static` badges, 2 skills, `research-concierge`, 1 native tool.
2. Register a new stdio MCP server from the UI → its tools appear with `{server}.{tool}` keys.
3. Create custom skill `summarize-site` from those tools + persona; badges appear on both Tools and Skills pages.
4. Toggle `direct_exposure` on one tool; verify next chat's trace shows a rung-1 `route` step.
5. Build custom sub agent with a branch, an error edge, and an HITL node; introduce a validation error, see it rejected inline, fix, save.
6. Chat: multi-turn — message 1 invokes the new sub agent (approve the HITL card mid-run); message 2 is a follow-up referencing message 1's result and succeeds using conversation history.
7. Ask something no sub agent covers → trace shows rung-4 ephemeral `dynamic` worker.
8. Kill the new MCP server process → invoke again → error edge path taken, run completes via fallback branch; server shows `error` status; reconnect from Settings.
9. Runs page: full trace with nested native-tool steps, tokens, route reasons; cancel a running run; retry a failed one.
10. Settings: change planner model → next run's trace labels show it; if a second provider key is configured, switch `default_model` to that provider (e.g. `google_genai:gemini-2.5-pro`) and rerun step 6's chat successfully — same registries, same code; open HITL queue; purge run history.
11. Switch `orchestrator_mode` to `agentic`, repeat step 6's first message: todo events stream, the same sub agent is reachable as a dispatch tool, HITL card still pauses/resumes, and the run trace remains label-comparable to the graph-mode run. While the agentic loop is mid-conversation, plug one more MCP tool and confirm it's callable within the same session (middleware live-sync).

All eleven pass = POC proven.

## 15. Deferred: Evals (post-POC — design must not block it)

Not built in the POC, but the POC design must leave these seams open:

- **Eval definition**: spreadsheet upload (xlsx/csv) in a predefined format — columns: `level (skill|sub_agent)`, `target_id`, `input` (task/query), `expected` (reference answer or criteria), `judge_notes` (optional grading guidance). Uploaded and run from the skill / sub agent detail pages.
- **Harness = existing machinery**: skill-level evals run the target as a single-skill ephemeral worker (the rung-4 factory path, unchanged); sub-agent-level evals invoke the full compiled agent. Config snapshots make every eval row reproducible against the exact definition evaluated; eval runs are ordinary runs tagged `eval=true` in the §10 label set, HITL nodes auto-approved in eval mode.
- **Results publishing**: to LangSmith — local instance or remote. Endpoint and enable-toggle via `app_settings` (`langsmith_enabled`, endpoint key); **API key stays env-only** (`LANGSMITH_API_KEY`), consistent with the no-keys-in-DB/UI rule, even when the user supplies a remote key. With LangSmith disabled, eval runs are still fully recorded in Postgres run traces and structured logs — only the dataset/experiment publishing step is skipped.
- **Why the POC already supports this**: the factory builds arbitrary single-skill workers, snapshots freeze configs, settings hot-reload, and the trace label set carries tier/kind/entity — the eval feature is an upload parser, a batch runner, and a publisher. No schema or architecture change anticipated.
