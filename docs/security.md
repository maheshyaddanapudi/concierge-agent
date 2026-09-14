# Security Posture (POC)

This document describes the security posture of the Concierge Agent proof of concept honestly: what is protected, what is deliberately not, and what that means for how you may run it.

**A note on §1.** The spec's original non-goals paragraph listed authentication/authorization, multi-tenancy, production hardening, rate limiting, and secrets-management-beyond-env as out of scope. Three of those were later **promoted in scope**: §18.8 shipped auth and tenancy (dark by default) and an unconditional rate limiter, §20 turned auth into a documented fork seam, and PLAN M49–M56 is production hardening by name. What still stands from that paragraph is the **secrets** non-goal: there is no secrets manager, no vault integration, no encryption at rest — env vars and, for MCP/A2A credentials, a write-only column with `env:VAR` indirection. Read the sections below, not the original paragraph.

## Explicit non-goals

- **No authentication or authorization ships — the seam does.** Every API endpoint under `/api/v1` and every admin page is open to anyone who can reach the port in the default deployment. Since M55 (spec §20) the repository carries the `AuthProvider` port a fork plugs its own auth into (`docs/extending.md`) and a builtin provider that is dark unless `AUTH_ENABLED=true` (spec §18.8: hashed sessions, an admin gate, per-user rows). The stance is deliberate: authentication is your organisation's, and the core's job is to ask the port wherever work is read — REST list and detail endpoints, both SSE streams, memory recall, run ownership — so that your rule holds in one place. It does not yet hold on every *action* endpoint; see **Known gaps** below before you rely on it to keep two parties apart.
- **No multi-tenancy.** One database, one registry set, one shared conversation history. Every operator sees and controls everything.
- **Trusted-operator assumption.** The admin UI is a command center for a trusted operator on a trusted network. **Registering a stdio MCP server is registering a subprocess**: `POST /mcp-servers` with `transport=stdio` makes the backend spawn `command args` inside its own container, with its own privileges, from an API call (`backend/app/mcp/manager.py`, spec §5). Since the M56 hardening wave the *launcher* is allowlisted (below), which narrows that considerably but does not close it — `npx -y <anything>` still fetches and runs arbitrary code. **Treat the ability to register an MCP server as the ability to execute code in the backend container.** This is by design for a POC and is the single most important fact on this page.

**The stdio launcher allowlist, precisely** (`stdio_allowlist()` / `_check_stdio_launcher` in `backend/app/mcp/manager.py`). Commands are matched by **basename**, so an absolute path to an admitted launcher is accepted and a lookalike elsewhere on `PATH` is not. Six launchers ship admitted — `uvx`, `npx`, `uv`, `node`, `python`, `python3` — plus whatever an operator names in **`MCP_STDIO_ALLOW`** (comma-separated). There is no separate entry for the acceptance stub server: it is launched as `python /app/tests/stub_mcp_server.py`, so it rides in under `python` like anything else. Enforcement is at **three** points, not two: `POST /mcp-servers` and `PATCH /mcp-servers/{id}` each refuse with a **422** naming the allowlist (the PATCH check matters — without it you could register as `npx` and then edit the command to anything), and the connect path checks again before spawning, which is what also covers rows written straight to the database by the seed. `MCP_STDIO_ALLOW` is not listed in `.env.example`; set it anyway.

**Deployment implication: never expose this stack to the public internet as-is.** Run it on localhost or a private, access-controlled network segment.

**CORS, precisely** (`backend/app/main.py`): the origin list is
`[FRONTEND_ORIGIN] if auth is enabled and FRONTEND_ORIGIN is set, else ["*"]`.
So the default really is permissive — and, importantly, **setting `FRONTEND_ORIGIN` alone does nothing**: it is only honoured when the active auth provider reports itself enabled. A stack running dark (`AUTH_ENABLED` unset, the shipped default) serves `allow_origins=["*"]` whatever `FRONTEND_ORIGIN` says. `X-Total-Count` is the one exposed response header either way.

**But pinning both does not currently work for a genuinely cross-origin UI.** The middleware stack is `LimitsMiddleware → AuthMiddleware → CORSMiddleware → app`, so `AuthMiddleware` sees a request *before* the CORS layer can answer it — and it does not exempt `OPTIONS`. With `AUTH_ENABLED=true`, a browser preflight for `PATCH /api/v1/settings` is answered **401 with no `Access-Control-Allow-Origin` header**, so the browser never sends the real request. This is invisible in the shipped compose because nginx serves the SPA and the API on one origin, where no preflight happens; it bites the moment the admin UI lives somewhere else. Until `OPTIONS` is exempted from the auth guard, **terminate CORS at a proxy you control** and keep the UI same-origin with the API.

**What auth does not cover, even when it is on.** `AuthMiddleware` only guards paths under `/api/v1`, so `/metrics`, `/health` and `/ready` are unauthenticated in every configuration — deliberate (a probe cannot hold a session), fine for a lab, unacceptable on a public address. Two `/api/v1` paths are explicitly exempt as well (`_EXEMPT` in `backend/app/auth/__init__.py`): `POST /auth/login`, which has nothing to authenticate with yet, and `POST /routines/{id}/fire`, which carries its own hashed **fire token** — that token *is* the authentication for the endpoint, so treat it like a password and re-issue it if it leaks.

## Inbound limits — the one control that is on by default

`backend/app/limits.py` runs **outermost, before `AuthMiddleware`, and does not consult it**. It is therefore the only protection a dark stack actually has, and it applies to every request whether or not anyone is logged in:

- **A request-body cap.** `MAX_REQUEST_BYTES` (default **2 MiB**) on every POST/PUT/PATCH, raised to `MAX_UPLOAD_BYTES` (default **8 MiB**) for the eval dataset upload alone. It is checked against a declared `Content-Length` *and* while a chunked body streams, so an undeclared body cannot walk past it one chunk at a time; over the limit is a **413**. This exists because nothing else bounded a body — not the app, not uvicorn, not nginx — and one large POST to `/chat` or `/settings` was an out-of-memory kill of the single process that serves everything.
- **A token-bucket rate limit**, default **120 burst / 10 per second**, over **429**. The earlier limiter lived inside `AuthMiddleware` behind `provider.enabled()`, so the shipped configuration — auth dark — had no limit at all; this one does not depend on auth. With auth on, the per-principal bucket still applies on top of it.

Three things to know before you rely on it:

1. **It is keyed on `request.client.host`, and the shipped compose topology destroys that key.** The frontend nginx proxies `/api/` without setting `X-Forwarded-For` or `X-Real-IP`, and uvicorn runs without `--proxy-headers`, so every request arriving through the SPA presents the *nginx container's* address. All browser traffic therefore shares **one** bucket: a weaker per-attacker limit, and a self-DoS vector where one abusive client spends everyone's budget. Only calls to the directly-published backend port carry a real peer address. If you put a proxy in front (you should), forward the client address and run uvicorn with `--proxy-headers` — otherwise the same collapse happens one layer out.
2. **The rate limit's shape is a runtime setting, not env.** `rate_limit_burst` and `rate_limit_per_s` live in `app_settings` and are read live per request, which means `PATCH /api/v1/settings` can raise them — and on a dark stack that endpoint is unauthenticated. The body cap is genuinely env-only. (`limits.py`'s own module docstring still claims both are env; the settings store is the authority.)
3. **`/health`, `/ready` and `/metrics` are exempt from both**, and both SSE streams are exempt from the rate limit (a stream holds one connection for a whole run).

The limiter fails **open**: if the shared bucket store is unreachable the request is allowed and a `rate_limit_store_unavailable` warning is logged. That is availability over enforcement, chosen deliberately — it also means a limit you cannot see in the logs is a limit that may not be running.

## Secrets

**Provider API keys are env-only — never in the database, never in the UI, never logged.** Enforcement points:

- `backend/app/config.py` — the only place secrets are read, via pydantic-settings from the environment. Its module docstring states the rule. The full inventory, not a sample:
  - **provider keys** — `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, **`OPENROUTER_API_KEY`**, and the custom gateway's **`CUSTOM_GATEWAY_API_KEY`** (with `CUSTOM_GATEWAY_BASE_URL` / `_MODELS`);
  - **`LANGSMITH_API_KEY`** — key only; enable/endpoint/project are runtime settings;
  - **`SMTP_PASSWORD`** (with `SMTP_USER` / `_HOST` / `_FROM` / `_TO`) for the §18.4 email channel;
  - **`AMBIENT_WEBHOOK_URL`** — not named like a secret, but a webhook URL routinely embeds its own token; treat it as one;
  - **`REDIS_URL`** and **`DATABASE_URL`**, both of which may carry credentials.
  Before any error text is persisted, returned or logged, it passes through `backend/app/sanitize.py` (M52), which redacts in two layers: the secret **values** this process knows, and credential **shapes** by pattern (URL userinfo, `Bearer …`, `sk-`/`AKIA`/`xox`/`gh*_`/`AIza` prefixes, and `key=value` pairs whose key names a secret).
  **Two caveats, both real.** The *values* layer covers the five provider keys, `LANGSMITH_API_KEY`, `SMTP_PASSWORD`, and the password component of `REDIS_URL` / `DATABASE_URL` — it does **not** include `AMBIENT_WEBHOOK_URL`, so a webhook whose token sits in the URL *path* (the common Slack/Teams shape) is redacted by neither layer and lands verbatim in the delivery channel ledger, which the Ambient → Inbox page renders. Until that is fixed, prefer a webhook that authenticates with a header over one that authenticates with its path, or terminate it at a relay you own. And the shape layer is a net, not a guarantee: a credential in a format it does not recognise passes through.
- `backend/app/settings_store.py` — the `app_settings` key-value store has no key-shaped setting; the `DEFAULTS` dict deliberately omits anything secret. The LangSmith *enable/endpoint/project* live here; the *key* does not.
- `frontend/src/pages/SettingsPage.tsx` — the page subtitle says it outright: "API keys stay env-only, never here." The Providers panel shows only `configured` / `no api key` status, never a value.
- `backend/app/obs.py` — the per-run LangSmith tracer reads `LANGSMITH_API_KEY` from config, never from settings.
- `REDIS_URL` (which may embed credentials) follows the same rule: env-only, and selecting the `redis` cache mode merely pings it (`settings_store._ping_redis`).

**What IS stored in the database** (Postgres is the single stateful service):

- The three registries (tools, skills, sub agents) plus `mcp_servers` records. Note: **stdio env vars and HTTP headers for MCP servers are stored in the DB** (`env`/`headers` jsonb columns, spec §3.1) — these may contain credentials *for those servers*. Since M52 they are **write-only**: every read returns them masked (`***`), a PATCH that sends `***` back keeps the stored value, `null` removes a key, and a value of the form `env:VAR_NAME` is resolved from the backend's environment at connect time so the credential never lands in the database at all (`backend/app/mcp/secrets.py`, the same pattern as A2A credentials, spec §19.3). The MCP Servers page shows only which keys are set. They are still plaintext at rest when stored literally — prefer the `env:` indirection for anything you cannot afford to have in an unencrypted database.
- Conversations, runs, and run steps — including **full step inputs and outputs** (tool arguments and results, model outputs). Anything a tool reads ends up in the trace store.
- LangGraph checkpoints (HITL pause/resume state), app settings, and retrieval embeddings.

## Trust boundaries

```
operator ──► admin UI ──► backend ──► MCP servers (subprocess / remote HTTP)
                              │             │
                              ▼             ▼
                          Postgres    tool results ──► model context ──► answers/actions
```

- **MCP servers are the largest boundary.** A stdio server is a subprocess in the backend container; an HTTP server is a remote endpoint you chose to trust. A malicious or compromised MCP server can: return poisoned tool results (which **feed directly into model context** and can steer the run — classic indirect prompt injection), lie about its tool list (`tools/list` output becomes registry records, and its descriptions are read by the planner), exfiltrate whatever arguments the model passes it, and — for stdio — do anything the backend container can do.
- **Prompt-injection exposure is real and only partly mitigated.** The seeded `fetch` MCP server pulls arbitrary live web content; the `web-research` skill feeds it into the model. Fetched pages and MCP tool outputs are untrusted input to the LLM. The structural mitigations: skills see only their bound tools (strict isolation, spec §3.3/§7.0), the filesystem MCP server is sandboxed to the `/workspace` volume, and consequential actions can be gated. Since M52, every string the platform itself knows to be external — remote-agent output, fired-event payloads, poll items, delivery bodies, candidate answers under evaluation, member memories, watch requests, the remembered-context block — is rendered through **one fence choke point** (`backend/app/untrusted.py`): any fence-shaped tag inside the payload is neutralized and the fence's opening and closing tags carry a per-render random token, so a payload can neither close the fence early nor forge one; the prompt golden sets pin the tokened prompts. What this does NOT cover: a tool result the model reads inside a skill loop (the `fetch` page itself) is still raw model input — the fence protects the platform's own prompts, not the model's reasoning over tool output.
- **Outbound fetches are under one egress policy (M52).** Every URL the platform fetches on someone else's say-so — an A2A agent card and its calls, an `http_json`/`rss` poll source, an HTTP MCP server, the webhook channel — is judged by `backend/app/egress.py`: `EGRESS_POLICY=public` (the default) refuses loopback, link-local (cloud metadata), private, reserved, multicast and unspecified targets by literal address and by what the name resolves to, except hosts the operator names in `EGRESS_ALLOW_HOSTS` (the way to admit an internal MCP server or agent); `allowlist` admits only those hosts; `open` keeps only the caps. Every redirect hop is re-checked in the client's request hook (at most five), bodies stream and are cut past `EGRESS_MAX_BYTES`, feeds parse with `defusedxml` off the event loop, and a refusal has one shape — `egress refused: <kind>` — so it cannot be used to map a network. Not covered: the stdio `fetch` MCP server makes its own connections from its own process; the egress policy governs the backend's clients, not a subprocess's.
- **Error text is sanitized before it is stored, returned, or logged (M52).** `backend/app/sanitize.py` replaces every secret value the process knows (each key-shaped config field, the credentials of the record being handled) and every credential shape (bearer tokens, well-known key prefixes, `key=value` pairs naming a secret, URL userinfo) with `[redacted]` — applied to run and step errors, MCP and remote-agent `last_error`, task errors, routine reasons, delivery ledgers, API error details, and as a structlog processor on every log line.
- **Authored regexes are bounded (M52).** Trigger and watch filters of op `regex` pass a static guard at the API (length, nested repetition, backreferences — the catastrophic-backtracking shapes) and again before every match, which runs in a worker thread under a timeout; a hostile pattern costs a quarter second of a worker thread, never the ambient tick.
- **HITL gates are the human control point.** A `hitl` node in a sub agent workflow pauses the run at a checkpoint until a human approves, denies, or answers a form gate (`POST /runs/{id}/hitl`). If you want a human between "model decided" and "tool acted" (e.g. before writing files), put a gate in the workflow — nothing else stands there.
- **The overlap judge is advisory only** (spec §4). It is an LLM-as-judge duplicate check on registry saves, it fails open on any error, and the save endpoints are unguarded. It is a hygiene feature, not a security control — do not mistake it for one.

## Known gaps: run-plane surfaces that do not ask the port

With `AUTH_ENABLED=true`, tenancy is enforced where a row is **read** — `GET /runs` filters through `scope_to_user`, `GET /runs/{id}` and `DELETE /runs/{id}` check `owns_row` — but a set of **action** endpoints was left to a future auth workstream and checks nothing. Measured against a two-member deployment, with one member acting on the other's run:

| Surface | Ownership check | What a member can do to another member's work |
|---|---|---|
| `POST /runs/{id}/hitl` | **none** | Approve or deny *anyone's* paused human gate, and answer its form questions |
| `POST /runs/{id}/cancel` | **none** | Cancel any run, anywhere in the fleet |
| `POST /runs/{id}/retry` | **none** | Re-plan any failed run — which spends provider tokens on someone else's message |
| `DELETE /runs` (purge all) | **none, and no admin gate** | Delete **every run, step and checkpoint for every user** in one unconfirmed call |
| `GET /ambient/ledger` | **none** | Read the whole fire/hold audit across all users |

The purge row is the sharpest: the builtin's admin gate (`_ADMIN_WRITE` in `backend/app/auth/builtin.py`) covers `mcp-servers`, `remote-agents`, `tools`, `skills`, `sub-agents` and `settings` — it does **not** cover `runs`, so destroying the entire run history is a plain member action. And the HITL row undercuts the control the section above calls "the human control point": with these gaps open, *any* authenticated human can be that human.

This is a **deliberate deferral, not a claim of safety**. Until it closes, `AUTH_ENABLED=true` should be read as "separates users' *views* of their work", not "separates users". Do not use it as the boundary between parties who should not be able to act on each other.

What *is* enforced end-to-end: both SSE streams. The run stream checks `owns_row` before it opens; the ambient delivery stream re-asks the port with `may_see` on **every event**, against the principal captured when the subscription opened (`backend/app/api/ambient.py`). Memory reads carry the provider's `memory_visibility` fragment. Those three were the M55 drill's findings and they hold.

## Model output handling in the UI

Model output is treated as data, never as markup:

- **Markdown answers** render through `react-markdown` in `frontend/src/components/Markdown.tsx` — React elements only, no raw-HTML pass-through (no `rehype-raw`, no `dangerouslySetInnerHTML` anywhere in `frontend/src`). A model that emits `<script>` gets literal text.
- **Structured summaries (A2UI)** are protocol messages rendered by the official `@a2ui/react` renderer (`frontend/src/components/AnswerUiView.tsx`) — "payloads are data, never markup." The component tree itself is generated server-side against a whitelisted schema (`backend/app/orchestrator/answer_ui.py`) and translated deterministically into A2UI v0.9; invalid payloads render nothing.
- **Charts** are pure themed SVG built by `frontend/src/components/ChartSvg.tsx` from specs validated by the `render_chart` native tool's pydantic schema (`_ChartSpec` in `backend/app/native/tools.py`: kind ∈ {bar, line, pie}, numeric series length-checked against labels). No markup surface.

## Network and dependency notes

- Three compose services (`docker-compose.yml`): `db`, `backend`, `frontend`. Published ports: frontend `${FRONTEND_PORT:-5173}→8080` (the container's nginx listens on 8080, not 80, because it runs unprivileged), backend `${BACKEND_PORT_RANGE:-8000-8010}→8000` — a **range**, one host port per replica under `--scale backend=N`, *not* `BACKEND_PORT` — and, only under the optional `redis` profile, Redis bound to `127.0.0.1:6379`. Postgres publishes no host port. Ask `docker compose port backend 8000` for the port a given replica actually got.
- The frontend nginx (`frontend/nginx.conf`) proxies `/api/` and `/metrics` to the backend; everything else serves the SPA. The backend port is also published directly, so the API is reachable on two ports.
- No message broker, no task queue, no Celery — smaller attack/ops surface, one process to reason about.

## Hardening checklist before any real deployment

1. Put an authenticating reverse proxy (or real authn/authz) in front of both the UI and the API; remove the direct backend port publish.
2. Keep the admin UI **same-origin** with the API and terminate CORS at the proxy in step 1. Setting `FRONTEND_ORIGIN` + `AUTH_ENABLED=true` pins the origin list, but it does not make a cross-origin UI work — the auth guard 401s the preflight (above). `FRONTEND_ORIGIN` by itself, without auth on, leaves CORS at `*`.
3. Constrain stdio MCP registration — UI-supplied `command`/`args` is remote code execution. The six-launcher allowlist bounds *which binary* starts, not what it then runs, so **shrink it**: `MCP_STDIO_ALLOW` only adds, it cannot remove, so a deployment that seeds only `uvx` and `npx` should have the other four taken out of `stdio_allowlist()` in the fork. Keep the rest of the defence in depth: the backend container already runs **non-root** (`concierge`, uid/gid 1000); add a read-only FS and seccomp/AppArmor.
4. Use the `env:VAR_NAME` indirection for MCP server `env`/`headers` values (or a secrets manager), and encrypt the database at rest; run traces contain tool inputs/outputs.
5. Keep `EGRESS_POLICY=public` (or an explicit allowlist) — and remember the stdio `fetch` server is a subprocess outside it: sandbox or remove it if the backend can reach anything sensitive.
6. Protect `/metrics`, `/health` and `/ready` at the proxy — they are unauthenticated in every configuration.
7. Make the inbound rate limit real: forward the client address from your proxy and run uvicorn with `--proxy-headers`, or the shipped topology gives all browser traffic one shared bucket. Lower `MAX_REQUEST_BYTES` from 2 MiB if nothing you run needs it, and remember `rate_limit_burst`/`rate_limit_per_s` are raisable through `PATCH /settings`.
8. Do not treat `AUTH_ENABLED=true` as an isolation boundary between users who should not act on each other — see *Known gaps* above. Put the real boundary at step 1.
9. Review every HITL-less workflow that binds write-capable tools; add gates before irreversible actions — and note that with auth on, any authenticated user can currently resolve any gate.
10. Add TLS everywhere (compose ships plain HTTP), and pin/scan images and dependencies.
