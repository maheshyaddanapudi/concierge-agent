# Code-level production-readiness review — `concierge-agent`

**Branch**: `prod_hardening` (cut from `dev`, HEAD `6bede07`)
**Lens**: implementation quality and correctness. Architecture/systems is covered by a parallel review.
**Out of scope by explicit decision**: authentication, authorization, RBAC. Security that is *not* authn/authz (secret leakage, injection, SSRF, unsafe deserialization, resource exhaustion, untrusted model/remote output) is in scope and is reported.
**Method**: every finding below was traced in the actual source, not from docstrings or `spec.md`. Where a claim depends on library behavior I say so.

There are **no Critical findings**. The highest-severity items are reachable resource exhaustion, a wedged autonomous plane, and three secret/data-exposure paths.

---

## High

### H1 — `GET /runs` (polled every 3 s by the UI) loads the entire `run_steps` table on every request

**Evidence**
- `backend/app/models/run.py:78-80` — `Run.steps` is `relationship(..., lazy="selectin")`.
- `backend/app/models/run.py:27` — `Conversation.runs` is also `lazy="selectin"`.
- `backend/app/api/runs.py:89-96` — `list_runs` does `select(Run).order_by(Run.started_at.desc())` with **no limit and no loader override**. `_run_out(r)` (line 61) does not read `r.steps`, but the selectin loader has already fired.
- `backend/alembic/versions/ebf05a862e33_initial_schema.py:219-245` — `run_steps` is created with a PK on `id` and FK constraints only. **There is no index on `run_steps.run_id`.** Postgres does not auto-index foreign keys.
- Same migration, `runs` (line 144-169): no index on `conversation_id`, `status`, or `started_at`. `tools.mcp_server_id` (line 184-214) is also unindexed.
- `frontend/src/api/hooks.ts:55-60` — `useRuns()` sets `refetchInterval: 3000`.

**What the code actually does**: one `GET /runs` emits `SELECT … FROM runs ORDER BY started_at DESC` (seq scan + sort, no index) followed by SQLAlchemy's selectin batch `SELECT … FROM run_steps WHERE run_id IN (…)` — a sequential scan of `run_steps` — and materializes every `RunStep` as a Python object. `GET /conversations` (`backend/app/api/chat.py:70-90`, which only needs `len(c.runs)`) chains both loaders: all conversations → all runs → all run steps.

**Failure scenario**: ambient mode on, one routine on a 60 s tick. After a week that is ~10 k runs and, at ~15 steps each, ~150 k `run_steps` rows carrying JSONB `input`/`output`. The Runs page open in one browser tab issues this every 3 seconds. Each request seq-scans and instantiates 150 k ORM objects with their JSONB payloads; latency climbs into tens of seconds, the connection pool (default `pool_size=5`, `backend/app/db.py:22` sets no sizing) saturates, and the process RSS spikes per request. Chat, SSE and the ambient tick all queue behind it.

**Remediation** (small): add `Index("run_steps_run_idx", "run_id")`, `runs(conversation_id)`, `runs(started_at DESC)`, `runs(status)`, `tools(mcp_server_id)` in a migration; change `Run.steps` and `Conversation.runs` to `lazy="raise_on_sql"` or `"select"` and load explicitly with `selectinload()` only in `get_run`; paginate `list_runs`/`list_conversations` (`limit`/`offset`), and use `select(func.count())` for the conversation run count.

---

### H2 — `RunEventBus` keeps every run's complete event history in process memory forever

**Evidence**
- `backend/app/orchestrator/context.py:12-49` — `RunEventBus._runs: dict[UUID, dict]`; `emit()` appends every event to `entry["history"]` unconditionally; entries are removed **only** by `forget(run_id)`.
- `backend/app/orchestrator/runner.py:632-633` — `forget_run_events` is the only caller of `forget`.
- `backend/app/api/runs.py:103` and `:143` — the only two call sites: `DELETE /runs` (purge-all) and `DELETE /runs/{id}`.
- `backend/app/orchestrator/recorder.py:40-41` — `emit()` is called on every step start, every step finish, every token, every activity transition, plan, route, dispatch, chart, and answer_ui.

Nothing in the run's own completion path (`runner._execute`, lines 171-213) forgets the run. `EVENT_BUS` is a module-level singleton, so this is process-lifetime retention.

**Failure scenario**: the operator never uses the delete/purge buttons (there is no automatic retention job). Each run retains its full SSE event list — for a multi-step agentic run with token streaming that is hundreds of dicts including the answer text. Ambient mode generates runs autonomously and forever. RSS grows monotonically until the container is OOM-killed, taking every in-flight run, the MCP subprocesses, and the leader lease with it.

Secondary: `RunEventBus._entry()` (line 18) uses `setdefault`, so `is_done(run_id)` and `unsubscribe(run_id, q)` **create** an entry for any UUID passed in — including one that never existed.

**Remediation** (small): bound `history` (ring buffer, e.g. last 500 events) and drop the entry a short TTL after the terminal event; make `is_done`/`unsubscribe` read-only (`self._runs.get(...)`) instead of `setdefault`.

---

### H3 — The ambient drain holds `FOR UPDATE` row locks and an open transaction across LLM judge calls

**Evidence**
- `backend/app/ambient/drain.py:65-107` — `drain_once` opens one session, claims up to 20 rows with `SELECT id … FOR UPDATE SKIP LOCKED`, then **inside the same `async with` block** loops `outcome = await _processor(event)` and only commits at line 107.
- `backend/app/ambient/decide.py:131-150` — the registered processor is `process_event`.
- `backend/app/ambient/decide.py:218-245` → `_intent_fire` → `_judge_significance` (line 85-128) — a full `structured.ainvoke(prompt)` model round-trip.
- `backend/app/ambient/decide.py:158, 192, 254` — the processor also opens **its own separate sessions** (a second pooled connection) while the drain's transaction is open.
- `spec.md:823` states the rule explicitly: "never holding a DB transaction across an LLM call".

**Failure scenario**: a poll source returns 20 fresh items for a standing intent with a `semantic_predicate`. `drain_once` locks 20 `ambient_events` rows and runs 20 sequential judge calls. On a reasoning model at 10-30 s each, the transaction stays open for 3-10 minutes: an idle-in-transaction connection held out of a 5-connection pool, `ambient_events` blocked from vacuum, and any other writer to those rows blocked. If the process is killed mid-drain, all 20 verdicts are lost and re-judged (paid for twice) on restart.

**Remediation** (medium): claim + mark the rows in one short transaction (set a `claimed_at`/`claimed_by`), commit, then judge outside any transaction, then write the verdicts back in a second short transaction with a `WHERE verdict IS NULL` guard. Also cap the judged batch per tick.

---

### H4 — One malformed routine trigger permanently wedges the entire ambient leader tick

**Evidence**
- `backend/app/api/routines.py:33` and `:47` — `triggers: list[dict[str, Any]] | None`. There is **no schema validation** of trigger shape on create or patch; the list is stored verbatim (`routines.py:129`).
- `backend/app/ambient/triggers.py:79-82` — `_schedule_due` for `type: "once"` calls `datetime.fromisoformat(str(trig.get("at")))` with no guard. For `type: "interval"` it calls `int(trig.get("seconds", 3600))` with no guard.
- `backend/app/ambient/triggers.py:255-257` — in `evaluate_state_conditions`, `op = compiled.get("op", ">=")` and `threshold = float(compiled.get("value", 0))` sit **outside** the `try/except` that wraps only the probe call (lines 249-253). `compiled` is written by the LLM-driven `ambient.watch` compiler.
- `backend/app/ambient/drain.py:169-214` — inside `if leader:` the tick calls, in order and all inside one `try`: `evaluate_schedules()`, `poll_due_intents()`, `evaluate_state_conditions()`, `expire_pattern_deadlines()`, `fire_due_wakeups()`, `sweep_hitl_aging()`, `reap_stalled_runs()`, `drain_once()`, `evaluate_presence()`, `flush_deliveries()`, salience, learner, a2a poller.
- `backend/app/ambient/drain.py:225-226` — the only handler: `except Exception as exc: logger.warning("ambient_tick_failed", error=str(exc))`. No traceback, no metric, no state change.

**Failure scenario**: an operator (or the watch compiler) saves `{"type": "once", "at": "tomorrow 9am"}`. `evaluate_schedules` is the *first* call in the leader branch, so `ValueError: Invalid isoformat string` aborts the whole tick body before anything else runs. Every subsequent tick repeats it. Result: no schedules fire, no polls run, no events drain, no deliveries flush, no stalled runs are reaped, no parked A2A tasks are rechecked — the ambient plane is silently dead, indefinitely, with one `warning` line per minute as the only signal.

**Remediation** (small-medium): validate `triggers` with a discriminated Pydantic union at the API boundary (reject at 422); wrap each evaluator in its own `try/except` inside the leader branch so one failure does not abort the others; log with `logger.exception` and increment an error metric; consider auto-pausing a routine whose trigger fails to parse.

---

### H5 — Pinned memories bypass the project and tenant filters when injected into prompts

**Evidence**
- `backend/app/memory/rank.py:268-279` — `pinned_memories()` filters on `Memory.pinned.is_(True), Memory.status == "active"` and then, in Python, drops rows whose `scope == "conversation"` and conversation id mismatches. **There is no `project_key` predicate and no `user_id` predicate.**
- Contrast `backend/app/memory/rank.py:71-87` — `_filters_sql`, used by `recall()`, explicitly enforces `(m.scope != 'project' OR m.project_key = CAST(:project_key AS text))` with the comment "projects never leak sideways", and `(m.user_id = CAST(:auth_user_id AS uuid) OR m.user_id IS NULL)` under `auth_enabled()`.
- `backend/app/memory/inject.py:76` — `pinned = await pinned_memories(conversation_id)`; those lines are placed in the remembered-context block that goes into the model prompt (lines 74-78), separately from the correctly filtered `recall()` hits at line 84.
- `backend/app/api/memories.py:187-196` and `:233-234` — `POST /memories` and `PATCH /memories/{id}` both let any memory be pinned, including a `scope='project'` row.

**Failure scenario**: a user pins "Acme's renewal number is $X" in project `acme`. Every subsequent conversation — including one under `project_key='globex'` — receives that line in its always-injected profile block. With `AUTH_ENABLED=1` the same gap means user B's pinned memories are injected into user A's prompts and can be surfaced verbatim in A's answer.

**Remediation** (small): give `pinned_memories` the same signature and predicates as `recall` — pass `project_key`, apply the `_filters_sql` project and tenant clauses (or reuse `_filters_sql` directly). Add a regression test that pins a project memory and asserts it does not appear in another project's block.

---

### H6 — Server-side request forgery on registered A2A card URLs and ambient poll sources, with the exception text echoed back

**Evidence**
- `backend/app/api/remote_agents.py:88-91`:
  ```python
  try:
      card = await manager.fetch_card(body.card_url)
  except Exception as exc:
      raise HTTPException(422, f"could not fetch agent card: {exc}") from exc
  ```
  `body.card_url` is a bare `str` (`backend/app/schemas/remote_agent.py:17`) — no scheme allowlist, no host/CIDR denylist.
- `backend/app/a2a/manager.py:57-64, 139-142` — `split_card_url` accepts any scheme/netloc; `A2ACardResolver` fetches it over `self._http`.
- `backend/app/a2a/manager.py:266-282` — after registration, `build_client` derives the request target from the **fetched card's own `url`**, so a card can redirect all subsequent traffic to a different internal host.
- `backend/app/ambient/sources.py:116-128` and `142-153` — `http_json_source`/`rss_source` GET `config["url"]` with `httpx.AsyncClient(timeout=20.0, **follow_redirects=True**)` (line 57). `config` comes from the LLM watch compiler or the routine API.
- `backend/app/ambient/channels.py:100-125` — the webhook channel URL is env-only, so that path is fine.

**Failure scenario**: `POST /remote-agents {"card_url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}`. The fetch fails to validate as an `AgentCard`, but the 422 body carries the raw exception — a connect-refused, a timeout, a `404`, and a JSON-decode error are all distinguishable, turning the endpoint into an internal port/host scanner. With `follow_redirects=True` on the poll sources, an attacker-controlled public URL can 302 to an internal address and have the response body ingested as ambient event payload, which then reaches a model context.

**Remediation** (medium): resolve the hostname and reject loopback/link-local/private/multicast/reserved ranges before the request (re-resolve after each redirect, or set `follow_redirects=False` and validate each hop); restrict schemes to `http`/`https`; return a fixed error string to the caller and log the detail server-side only.

---

### H7 — MCP server `env` and `headers` are stored plaintext and returned verbatim by the registry API

**Evidence**
- `backend/app/schemas/mcp_server.py:41-51` — `McpServerOut` includes `env: dict[str, Any] | None` and `headers: dict[str, Any] | None` as plain output fields.
- `backend/app/schemas/mcp_server.py:12-21, 32-40` — both are freely writable on create and patch.
- `backend/app/mcp/manager.py:52-62, 140-141` — `env` is merged into the spawned process environment; `headers` are sent on the HTTP transport. These are exactly where an MCP server's `GITHUB_TOKEN`, `SLACK_BOT_TOKEN` or `Authorization: Bearer …` live.
- Contrast `backend/app/schemas/remote_agent.py:3-6, 25-40` — for A2A the codebase deliberately made `credentials` **write-only**: "it appears in Create/Patch bodies and is never present on any Out model — the UI sees per-scheme configured flags only". The MCP path never got the same treatment.
- `backend/app/mcp/manager.py:124` and `288-299` — connection failures store `_describe(exc)` in `mcp_servers.last_error`, which `McpServerOut.last_error` also returns.

**Failure scenario**: any `GET /api/v1/mcp-servers` response contains live credentials in cleartext. They land in the browser's network cache, in any reverse-proxy response log, in a support screenshot, and in every DB backup. This is a guaranteed exposure, not a conditional one, and it is inconsistent with the project's own established pattern one module over.

**Remediation** (small): mirror the remote-agent design — drop `env`/`headers` from `McpServerOut`, replace with `{key: {"configured": true}}` projections; support the same `env:VAR_NAME` indirection `app/a2a/auth.py:54-60` already implements so values need not be stored at all.

---

### H8 — Raw exception text from authenticated A2A calls is persisted and returned to clients

**Evidence**
- `backend/app/a2a/poller.py:131-136`:
  ```python
  except Exception as exc:  # recheck failure — retry next tick
      await tasks.update_task(row.id, parked=True, error=f"recheck failed: {exc}")
  ```
- `backend/app/api/remote_agents.py:263-264` — `raise HTTPException(502, f"reply failed: {exc}")`; `:287-288` — `raise HTTPException(502, f"remote cancel failed: {exc}")`.
- `backend/app/schemas/remote_agent.py:53` — `A2ATaskOut.error` is returned to the UI.
- `backend/app/a2a/auth.py:189-191` — the `apiKey` / `In.query` placement writes the credential into `http_kwargs["params"]`, i.e. into the request **URL**.

**Failure scenario**: a remote agent's card declares `apiKey` in `query`. The counterparty returns 401/500. `httpx.HTTPStatusError.__str__` includes the full request URL with its query string, so the credential is written into `a2a_tasks.error`, rendered in the Remote Agents task drawer, and returned in the 502 body. (This depends on the a2a SDK propagating httpx's message rather than substituting its own; the safe assumption is that it does.) Even without the query placement, these strings routinely carry internal hostnames and paths.

**Remediation** (small): sanitize before persisting/returning — strip query strings and known credential header names from exception text; return a generic message to the caller and `logger.exception` the detail server-side. Cover it with a test that asserts a query-placed credential never appears in `A2ATaskOut.error`.

---

### H9 — Untrusted RSS is parsed with `xml.etree` and poll responses are read unbounded

**Evidence**
- `backend/app/ambient/sources.py:25, 153` — `from xml.etree import ElementTree`; `root = ElementTree.fromstring(text)` on an arbitrary remote feed.
- `backend/app/ambient/sources.py:149-152` — `text = resp.text` with no `Content-Length` check and no streaming cap; `http_json_source` (line 126) does `resp.json()` the same way.

Python's own XML security documentation lists `xml.etree` as **vulnerable** to "billion laughs" and quadratic-blowup entity expansion (external entity expansion and DTD retrieval are safe). The whole application is a single asyncio process (`spec.md` §2 — no broker, no worker pool), so an OOM here is total.

**Failure scenario**: an operator adds an RSS watch on a feed that is later compromised, or that simply serves a 500 MB response. A 1 KB entity-expansion payload inflates to gigabytes inside `fromstring`, which is also **CPU-bound and blocking** — it stalls the event loop for every in-flight run and SSE stream before the process dies.

**Remediation** (small): switch to `defusedxml.ElementTree` (or add explicit entity rejection); stream the response and abort past a configured byte cap (e.g. 5 MB) for both `rss_source` and `http_json_source`; run the parse in `asyncio.to_thread` so a slow parse cannot block the loop.

---

## Medium

### M1 — `get_model()` constructs a brand-new provider client, with a new connection pool, on every model call

`backend/app/llm/registry.py:48-52` — `get_model` calls `provider.get_chat_model(...)` with no caching; every adapter (`backend/app/llm/adapters.py:130, 163, 219, 278, 336`) returns a freshly constructed `ChatAnthropic`/`ChatGoogleGenerativeAI`/`ChatOpenAI`, each of which builds its own SDK client and httpx connection pool.

Call sites are hot: `backend/app/ambient/decide.py:99` (every judge), `backend/app/factory/worker.py:292-309` (every skill node), `backend/app/native/tools.py:48`, `backend/app/memory/lifecycle.py:166`, plus the planner, aggregator and formatter per run. Under sustained load this means a fresh TLS handshake per LLM call, no keep-alive reuse, and a steady stream of httpx clients relying on GC finalizers to close their sockets — file-descriptor pressure and added latency on every call.
**Remediation** (small): memoize on `(ref, frozen params)` with an `lru_cache`-style dict; the adapters are already pure factories.

### M2 — Run token totals are read-modify-write and lose updates under parallel dispatch

`backend/app/orchestrator/recorder.py:161-165` and `backend/app/orchestrator/runner.py:276-281` both do `run.total_input_tokens += n` in an independently opened session. Parallel dispatch (`max_parallel_dispatch` default 4, `backend/app/settings_store.py:25`) runs several `finish_step` calls concurrently: each SELECTs the same value and writes back its own sum, so all but the last increment are lost. Token accounting — which the ambient supervisor uses as a **budget** (`backend/app/ambient/execute.py:186`) — silently undercounts.
**Remediation** (small): use an atomic `update(Run).values(total_input_tokens=Run.total_input_tokens + n)`.

### M3 — The default cache mode re-reads the whole settings table on every single setting lookup

`backend/app/registry_cache.py:359-360` — in `bypass` (the default, `settings_store.py:44`) `_ensure` calls `_load_registry` unconditionally, which for `"settings"` opens a session and runs `get_settings()` = `SELECT * FROM app_settings` (`backend/app/settings_store.py:220-226`). `RegistryCache.setting(key)` (line 475-478) is called ~15 times per ambient tick (`drain.py:151, 187, 235`, `decide.py:64, 96-97`, `deliver.py`, `channels.py:258, 263`, `poller.py:107, 110`, `fence.py:20`) and several times per run. Each is a full round-trip on its own pooled connection.
**Remediation** (small): make `_ensure("settings")` cache within a single request/tick even in bypass mode, or fetch the merged dict once per tick and pass it down.

### M4 — Every MCP tool invocation pays a full `tools/list` round-trip

`backend/app/factory/worker.py:176-186` — the lazy MCP proxy's `call` does `await manager.get_langchain_tools(UUID(server_id), [tool_name])` on each invocation, and `backend/app/mcp/manager.py:272-280` implements that as `load_mcp_tools(conn.session)` (a live `tools/list`) followed by a name filter. For a server exposing 40 tools, every single tool call ships and parses 40 schemas first.
**Remediation** (small): cache the materialized LangChain tools per `server_id`, invalidated by the existing `listChanged` handler (`manager.py:233-242`) and by `_ingest`.

### M5 — Consolidation jobs hold an advisory-lock session open across LLM and embedding calls, contradicting the module's own docstring

`backend/app/memory/lifecycle.py:344-355`:
```python
async with get_session_factory()() as session:
    if not await acquire_job_lock(session, job_id):
        continue
    try:
        results[name] = await fn()
```
`acquire_job_lock` (`backend/app/memory/scheduler.py:81-91`) issues a `SELECT pg_try_advisory_lock(...)`, which autobegins a transaction. `fn` is `reflection` (an `ainvoke` at `lifecycle.py:167`), `embedding_backfill` (embeddings API calls at `lifecycle.py:290`) or `_extraction_tuner_moves`. The session stays idle-in-transaction for the whole call. `backend/app/memory/lifecycle.py:3-4` claims these jobs "never hold a DB transaction across an LLM call" — the docstring has drifted from the code.
**Remediation** (small): `await session.commit()` immediately after acquiring the lock (the session-level advisory lock survives commit), or hold the lock on a dedicated connection outside a transaction.

### M6 — Consolidation sweeps `SELECT *` whole tables into Python

- `backend/app/memory/lifecycle.py:95-100` — `decay_sweep` loads every `active`, unpinned `Memory` row to compute an exponential in Python.
- `backend/app/memory/lifecycle.py:205-215` — `contradiction_sweep` loads every active row with an `entity_key`.
- `backend/app/memory/lifecycle.py:152-155` — `reflection` loads **all** `source='inferred'` rows just to collect cited ids.
- `backend/app/mcp/manager.py:192` / `backend/app/a2a/manager.py:194` — `select(Tool.tool_key)` loads the entire key set on every ingest.

These are unbounded in a store designed to grow indefinitely. `decay_sweep`'s formula is expressible in SQL; `reflection`'s cited-id set is a `jsonb` containment query.
**Remediation** (medium): push the decay predicate into SQL, add a `LIMIT`/batch loop to each sweep, and query cited ids rather than loading rows.

### M7 — LISTEN connections never reconnect; NOTIFY wakeups die silently

`backend/app/ambient/drain.py:135-147` — `_listen()` opens a dedicated `asyncpg` connection, adds a listener, then `await stop.wait()`. If Postgres severs the connection (restart, failover, idle timeout, connection reaper), `stop.wait()` never returns, the task is neither done nor raising, so the `listener_task is None or listener_task.done()` guard at line 153 never re-creates it. `backend/app/registry_cache.py:271-297` has the same shape: `start_listener` returns early when `self._listener_conn is not None` and nothing ever detects a dead connection.

Consequence: ambient event latency silently degrades from "on NOTIFY" to "on the ≥15 s tick", and cross-replica registry-cache invalidation stops entirely (stale tool/skill catalogs served by non-writing replicas until restart). Neither is logged.
**Remediation** (small): register an asyncpg termination listener (`conn.add_termination_listener`) or check `conn.is_closed()` each tick and rebuild.

### M8 — `RUNNING_TASKS` bookkeeping loses track of a run on concurrent resume

`backend/app/orchestrator/runner.py:88-91`:
```python
task = asyncio.create_task(_execute(run_id, resume=resume))
RUNNING_TASKS[run_id] = task
task.add_done_callback(lambda t: RUNNING_TASKS.pop(run_id, None))
```
The done-callback pops by key, not by identity. If a second task is registered for the same `run_id` before the first finishes, the first task's callback evicts the *second*. `resume_run` (line 562-577) checks `status == "paused_hitl"` and then starts a task with no lock, so two concurrent `POST /runs/{id}/hitl` calls both pass the check and start two tasks on the same checkpointer thread. After that, `cancel_run` (line 580-594) finds nothing in `RUNNING_TASKS`, falls through to `_finalize_failure`, and marks a still-executing run `cancelled`.
**Remediation** (small): `if RUNNING_TASKS.get(run_id) is t: RUNNING_TASKS.pop(run_id)`; guard resume with a conditional `UPDATE runs SET status='running' WHERE id=… AND status='paused_hitl'` and start the task only if a row was updated.

### M9 — `cancel_run` reports success when cancellation times out

`backend/app/orchestrator/runner.py:583-587` — `task.cancel()` then `with contextlib.suppress(BaseException): await asyncio.wait_for(task, timeout=10)` then `return`. If the run does not stop within 10 s (a shielded network call, a long MCP invocation), the suppress swallows the `TimeoutError`, no run-status row is written, and `POST /runs/{id}/cancel` returns `{"status": "cancelled"}` for a run that is still executing and will later write its own `completed` status.
**Remediation** (small): distinguish the timeout; return `202` with "cancellation requested" and leave the status alone, or mark `cancelling`.

### M10 — Poll-source watermark cap re-emits items for feeds larger than the cap

`backend/app/ambient/sources.py:80-96` — `_dedupe` appends fresh keys to the seen list and stores `json.dumps(seen[-_SEEN_CAP:])` with `_SEEN_CAP = 100` (line 36). A feed returning more than 100 items in one poll pushes the earliest keys out of the window; on the next poll those items look new again, are re-emitted, and push the *next* batch out — a permanent duplicate-event loop against a static feed.
**Remediation** (small): cap the number of items processed per poll below `_SEEN_CAP` (the emit loop already does `items[:20]` at `triggers.py:208`, but `_dedupe` rolls the watermark for **all** items before that slice — so 150 items also silently drop 130 events), or key the watermark on a monotonic cursor when the source provides one.

### M11 — Multiple schedule triggers on one routine starve each other

`backend/app/ambient/triggers.py:75-97, 111-140` — `_schedule_due` uses `routine.last_fired_at`, a single column per routine, as the anchor for **every** trigger in `routine.triggers`. Firing trigger index 0 stamps `last_fired_at = now`, which then advances trigger index 1's cron/interval baseline as if it had fired. A routine with a daily 09:00 cron and a daily 17:00 cron fires once a day, not twice.
**Remediation** (small): store per-trigger watermarks (`{index: last_fired}` jsonb) instead of one column.

### M12 — LLM-authored regexes run on the event loop (ReDoS)

`backend/app/ambient/decide.py:52` — `re.search(expect, value)` where `expect` comes from `intent.compiled["filters"]`, written by the `ambient.watch` compiler (an LLM) or by the routines API (`triggers: list[dict[str, Any]]`, unvalidated — see H4). A catastrophic-backtracking pattern such as `(a+)+$` against a long event payload blocks the single event loop for the whole process, stalling every run and SSE stream.
**Remediation** (small): pre-compile filters at save time and reject patterns over a length/complexity budget; run matching under `asyncio.to_thread` with a timeout, or use a linear-time engine.

### M13 — The SMTP delivery channel authenticates over an unencrypted connection

`backend/app/ambient/channels.py:91-97`:
```python
with smtplib.SMTP(cfg.smtp_host or "", cfg.smtp_port, timeout=15) as smtp:
    if cfg.smtp_user and cfg.smtp_password:
        smtp.login(cfg.smtp_user, cfg.smtp_password)
```
No `starttls()`, no `SMTP_SSL`, and the default port is `25` (`backend/app/config.py:28`). `SMTP_PASSWORD` — a real credential per the module's own "no secrets in the DB" comment — is transmitted in cleartext (LOGIN/PLAIN is base64, not encryption) to whatever host `SMTP_HOST` names.
**Remediation** (small): call `smtp.starttls()` before `login` and fail closed if the server does not offer it, or use `smtplib.SMTP_SSL`; make the mode configurable with TLS as the default.

### M14 — The session token is passed in the SSE query string, landing in access logs

`frontend/src/api/client.ts:23-26` — `sseUrl()` appends `?token=<session token>`; `backend/app/auth.py:199-202` accepts it. Uvicorn's access log records the full path and query string by default, as does every reverse proxy in front of it. The token is a bearer credential with a 24 h TTL (`auth.py:40`). `Referrer-Policy: no-referrer` is set (`auth.py:240`), which handles the referer leak but not the log leak. Reported as secret hygiene, not as an authn design question.
**Remediation** (small): issue a short-lived, single-use stream ticket for SSE instead of the session token, or move to a cookie the `EventSource` sends automatically.

### M15 — Stdio MCP servers run arbitrary commands as root inside the backend container

`backend/app/mcp/manager.py:132-138` — `command` and `args` come straight from the `mcp_servers` row and are passed to `StdioServerParameters`; there is no allowlist, no sandbox, and no resource limit. `backend/Dockerfile` never sets a `USER`, so the process (and every spawned server) runs as root, with the `workspace` volume mounted (`docker-compose.yml`). Beyond the obvious: spawned processes have no memory/CPU/lifetime cap, and `_teardown` (`manager.py:159-167`) only cancels the asyncio task — a stdio child that ignores stdin closure is not reaped.
**Remediation** (medium): add a non-root `USER` to the Dockerfile; add a configurable command allowlist (`uvx`, `npx`, absolute paths under a fixed prefix); set `--pids-limit`/memory limits on the backend service; verify child-process reaping explicitly.

### M16 — Remaining background-task/test-boundary hazards beyond the one already fixed

`backend/tests/conftest.py:57-66` drains only `memory_scheduler` before the per-test `TRUNCATE`. These other module-level task sets can still cross a test boundary and race the truncate, and `asyncio_default_test_loop_scope = "session"` (`pyproject.toml`) means tasks genuinely survive between tests:
- `backend/app/retrieval.py:247-256` — `_EMBED_TASKS` (write-path embedding refresh).
- `backend/app/ambient/drain.py:36, 112-114` — `_EXEC_TASKS` (the ambient executor; each spawns a full run).
- `backend/app/orchestrator/runner.py:34, 88-91` — `RUNNING_TASKS`.
- `backend/app/api/evals.py:151-153` — `_RUN_TASKS`.
- `backend/app/a2a/proxy.py:252` — detached `_cancel_cleanup` tasks.
- `backend/app/registry_cache.py:289-291` — `_listener_tasks`.

Separately, `conftest.py:10-13` pops `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `OPENAI_API_KEY` but **not** `OPENROUTER_API_KEY`, `CUSTOM_GATEWAY_API_KEY` or `LANGSMITH_API_KEY`. A developer with those exported gets different `validate_model_selection` outcomes (`backend/app/llm/registry.py:54-72` branches on `is_configured()`) and, for LangSmith, live network calls from the suite.
**Remediation** (small): add a shared `drain_background_tasks()` helper that awaits all six sets, call it in `_clean_tables`; pop the remaining provider keys in `conftest`.

### M17 — Frontend: a failed `/chat` post is an unhandled rejection and silently discards the queued draft

`frontend/src/pages/ChatPage.tsx:735-753` — `send()` has no `try/catch`; `await api.post('/chat', body)` throws `ApiError` on any non-2xx (`frontend/src/api/client.ts:47-56`). It is invoked as `void send(text)`.

`frontend/src/pages/ChatPage.tsx:769-771`:
```python
const text = queuedDraft.text
setQueuedDraft(null)
if (text.trim()) void send(text)
```
The draft is cleared **before** the send. A 429 (rate limit), a 503, or a 409 on a deactivated target sub agent discards the user's typed message entirely with no error shown anywhere. `stopRun` (line 754-757) at least uses `.catch(() => {})`, which is silent but not lossy.
**Remediation** (small): wrap `send` in `try/catch`, surface `ApiError.detail` in the composer, and restore `queuedDraft` on failure.

### M18 — `except BaseException` swallows `CancelledError` on the MCP and A2A paths

- `backend/app/mcp/manager.py:122` — `connect_server`'s failure handler catches `BaseException`; a cancel of the caller is turned into a recorded `error` status and a normal return.
- `backend/app/mcp/manager.py:153-157` — `_run_connection` stores `CancelledError` in `conn.error` and returns normally, so `_teardown`'s `wait_for` cannot distinguish a cancelled teardown from a failed connection.
- `backend/app/mcp/manager.py:254` — `ping_all` treats a cancellation as a failed ping and then does DB writes while cancelling.
- `backend/app/a2a/manager.py:153` — `refresh_agent` same shape.

During shutdown these make cancellation non-cooperative and can leave misleading `error` statuses on server rows.
**Remediation** (small): catch `Exception` and let `BaseException`/`CancelledError` propagate, or re-raise `CancelledError` explicitly.

### M19 — MCP health monitoring stops permanently after one transient error

`backend/app/mcp/manager.py:261-268`:
```python
async def _health_loop(self) -> None:
    while True:
        async with get_session_factory()() as db:
            interval = int(await get_setting(db, "mcp_health_interval_s"))
        await asyncio.sleep(max(interval, 1))
        await self.ping_all()
```
No `try/except` around the body. A single DB blip in `get_setting` (or an unexpected raise from `ping_all`'s teardown/`_record_status`) terminates the task. `self._health_task` stays non-`None`, so `start()` (line 93-94) will not recreate it. The exception is never retrieved, so it appears only as an asyncio warning. Dead MCP servers then keep `status='active'` in the registry and the UI indefinitely.
**Remediation** (small): wrap the loop body in `try/except Exception: logger.exception(...)`, and add a done-callback that logs and restarts.

### M20 — Unbounded remote A2A output held in memory and persisted

`backend/app/a2a/client_port.py:41-63` — `_task_text` joins every artifact's text with no cap, and `outcome_from_task` puts the whole thing in `RemoteOutcome.text`. `backend/app/a2a/proxy.py:199-201` writes it to `a2a_tasks.result_text` (an unbounded `Text` column). Truncation happens only at fence time (`backend/app/a2a/fence.py:28`), after the full string has been built and stored. A counterparty returning a 500 MB artifact spikes RSS and bloats the DB.
**Remediation** (small): cap accumulation in `_parts_text`/`_task_text` at the fence budget plus a margin, and truncate before persisting.

### M21 — `ToolsRegistryMiddleware`'s resolved-tool map is mutated while concurrent tool calls read it

`backend/app/orchestrator/middleware.py:144-145, 186-194, 201-214` — `self._current` and `self._meta` are per-instance mutable state. `awrap_model_call` re-resolves and reassigns both on every model call; `awrap_tool_call` may also call `_resolve()` (line 207) on a miss. LangChain executes a model turn's tool calls concurrently, so one call's `_resolve()` can swap `_meta` between another call's `self._current.get(name)` (line 203) and its `self._meta.get(name, {})` (line 211) — the step is then recorded with the wrong `kind`/`source`/`entity_id` labels, and a tool that vanished from the registry mid-turn falls through to `handler(request)` unresolved. `SkillsRegistryMiddleware._current` (line 274) and `SubAgentsRegistryMiddleware._current` (line 395) have the same shape.
**Remediation** (small): resolve into a local snapshot and read `(tool, meta)` as one lookup, or guard the swap with an `asyncio.Lock`.

### M22 — Ruff's configured rule set does not include the rules the code's own `# noqa` comments cite

`backend/pyproject.toml` — `[tool.ruff.lint] select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC"]`. Neither `BLE` (blind-except) nor `S` (bandit/security) is enabled. The repository carries **69** `# noqa: BLE001` comments and 2 `# noqa: S608` comments in `app/`, all of which are inert: `ruff check .` passes, and running `--select BLE001` explicitly still surfaces 4 unmarked blind excepts (`a2a/manager.py:246`, `a2a/poller.py:133`, `ambient/coordinate.py:47`, plus others without markers at `orchestrator/middleware.py:219`, `orchestrator/ladder.py:605`, `api/skills.py:54`, `api/sub_agents.py:42`, `api/remote_agents.py:91/264/288`, `native/tools.py:52`). The team's intended discipline — "every blind except is a deliberate, annotated decision" — is not machine-enforced, and new unannotated ones ship freely.
**Remediation** (small): add `BLE` and `S` (with a curated per-file ignore list) to `select`, plus `RUF100` so stale `noqa`s are flagged. Expect a one-time cleanup of the currently unmarked sites.

---

## Low

- **`workspace_disk_pct` probes an arbitrary caller-supplied path with a blocking syscall.** `backend/app/ambient/sources.py:225-231` — `shutil.disk_usage(config.get("path") or …)` with `path` from LLM-compiled watch config; it is a blocking `statvfs` on the event loop, and its raise/succeed behavior discloses whether an arbitrary host path exists. Constrain to the workspace volume and wrap in `to_thread`.
- **`ambient_digest_times` / `ambient_quiet_hours` accept invalid clock times.** `backend/app/settings_store.py:381` — `[0-2]\d:[0-5]\d` matches `29:59`. Use `datetime.strptime(v, "%H:%M")`.
- **Boolean values pass integer-setting validation.** `backend/app/settings_store.py:312` — `isinstance(value, int)` is `True` for `bool`, so `{"mcp_health_interval_s": true}` stores a boolean. Other keys (e.g. `ambient_salience_min_urgency`, line 327) correctly add `isinstance(value, bool)`; the general `_INT_KEYS` branch does not.
- **`RegistryCache.setting` raises a bare `KeyError` for an unknown key.** `backend/app/registry_cache.py:475-478` — `data[key]`. Most callers wrap in `except Exception`, so a typo'd key becomes a silent fallback rather than a startup error.
- **`get_checkpointer()` has no lock around lazy initialization.** `backend/app/db.py:43-62` — two concurrent first callers can each build a 10-connection `AsyncConnectionPool`; only one is retained, the other leaks. The lifespan warms it at line 50 so this is mostly unreachable in production.
- **Alembic runs on every replica at boot with no coordination.** `backend/app/main.py:19-31` — under `--scale backend=N`, N processes run `command.upgrade(head)` simultaneously.
- **Frontend toast timers are never cleared.** `frontend/src/components/AmbientToaster.tsx:44` — `setTimeout` per toast, no cleanup on unmount or effect teardown.
- **Auto-scroll effect has no dependency array.** `frontend/src/pages/ChatPage.tsx:731-733` — `scrollIntoView({behavior:'smooth'})` fires on *every* render, including every streamed token, which both costs frames and fights the user's own scrolling.
- **`Run.conversation_id` has no `ON DELETE` behavior.** `backend/app/models/run.py:36` — plain `ForeignKey("conversations.id")` while every sibling FK specifies `CASCADE`/`SET NULL`. There is no delete-conversation endpoint today, so it is unreachable, but it is a trap for the next person who adds one.
- **Container/compose hygiene.** `docker-compose.yml` — default `POSTGRES_PASSWORD: concierge`; `backend`/`frontend` publish on `0.0.0.0` while `redis` is correctly pinned to `127.0.0.1`; no `restart:` policy, no backend healthcheck, no resource limits. `backend/Dockerfile` — `FROM python:3.12-slim` without a digest and `pip install uv` unpinned (the Python dependency graph itself *is* pinned via `uv export --frozen`, which is good).
- **The bootstrap admin password is written to the log at WARNING.** `backend/app/auth.py:160-165` — deliberate and documented, but it means the credential persists in whatever aggregates the logs.
- **`langsmith_endpoint` / `otlp_endpoint` are free-form URLs settable at runtime.** `backend/app/settings_store.py:210, 393` — validated only as `isinstance(str)`; telemetry (including prompts, if LangSmith tracing is on) can be pointed at an arbitrary host.
- **Timing-dependent test waits.** `backend/tests/test_a2a_longrunning.py:160, 183, 259, 277, 290, 296` use fixed `asyncio.sleep(1.1-3.2)`; a dozen other files use `asyncio.sleep(0.1)` to wait for fire-and-forget tasks. `backend/tests/test_mcp_manager.py:66` already defines a proper `wait_for(predicate, timeout_s)` helper — promoting it to `conftest.py` and using it everywhere would remove a whole class of CI flakiness.

---

## What is already high quality

This is not a codebase that needs a lecture about discipline. Specific things that are genuinely well done:

- **The provider port is real and unbreached.** `app/llm/` is the only tree importing `langchain_anthropic`/`langchain_openai`/`langchain_google_genai`; every consumer goes through `get_model("provider:model")`. The `_ChatOpenRouter` subclass (`adapters.py:41-64`) is a textbook example of absorbing a vendor quirk *inside* the port instead of leaking a special case outward. The same isolation is applied recursively to `app/a2a/` for the a2a/authlib SDKs.
- **A2A credentials were designed write-only from the start.** `schemas/remote_agent.py` never emits `credentials`; the UI gets `{configured: bool}` projections; `env:VAR_NAME` indirection means values need not be stored at all. H7 is a finding precisely *because* this correct pattern exists one module away.
- **The comments carry hard-won operational truth, not restatement of the code.** `memory/rank.py:166-169` ("NEVER a raw `SELECT *` with positional column mapping … found live in M31"), `ambient/decide.py:132-134` ("a processor must never touch ambient_events itself — FOR UPDATE self-deadlock, found live"), `tests/conftest.py:68-74` (the sse-starlette `AppStatus` global leak), and the entire `backend/Dockerfile` readabilipy/undici section are all real incident write-ups embedded at the point of failure. That is unusually valuable.
- **The untrusted-output fencing is structural, not prompt-hoped.** `a2a/fence.py` is a pure, sync, deterministic function with a file-backed prompt; `proxy.py` fences on every exit path including the error path (line 211); `ambient/store.py` marks payloads `UNTRUSTED` at the emit site. `client_port.py:5-7` states the caller's obligation explicitly in the module docstring.
- **HITL replay idempotency is thought through end to end.** `a2a/tasks.call_key_for` + `find_open_task` (adopt, never re-send), `middleware.py:201-208` and `:375-380` (resolve the registry on a replayed tool call before any model call), `runner._pending_interrupts` (distinguishing stale from live interrupts across parallel supersteps), `ladder.find_running_dispatch` (don't double-record the route). These are the details that are usually wrong.
- **Cascade guards live at the write boundary.** `ambient/store.emit_event` enforces depth ceiling, no-self-trigger, per-source rate kill switch and dedupe in code before the insert — not in a prompt, not in the processor.
- **Migrations are complete and reversible.** Every one of the ~25 files in `alembic/versions/` has a real `downgrade()`, including data-preserving ones (`c3d4e5f6a7b8:32` deletes the rows that would violate the restored `NOT NULL` before altering the column).
- **The `M48` switchability work put the gate inside each job rather than in the dispatcher** (`memory/lifecycle.py:36-52` and the in-function `gate_open` calls), with a structural test asserting every `JOB_*` appears in `JOB_GATES`. That is the right call and it is documented with the reason.
- **The build is a gate, not a hope.** `python -m app.doclint` runs in the Dockerfile so a malformed `.skill.md` fails the build; the MCP prewarm deliberately refuses `|| true` and explains why.
- **Markdown rendering is safe by construction** (`Markdown.tsx` — react-markdown with no `rehype-raw`, no `dangerouslySetInnerHTML` anywhere in `frontend/src`), and the reason is stated in the file header.

---

## Top 5, in recommended fix order

1. **H1 — index `run_steps.run_id` (plus `runs.conversation_id/status/started_at`) and stop the `selectin` cascade on `/runs` and `/conversations`.** A one-migration + one-loader change that removes the most likely cause of the first production outage; the UI is already polling it every 3 seconds.
2. **H4 — validate `Routine.triggers` and isolate each ambient evaluator in its own `try`.** A single bad `"at"` string currently silences the entire autonomous plane with one warning line per minute; this is the cheapest fix with the worst failure mode.
3. **H5 + H7 — filter `pinned_memories` by project and tenant, and make MCP `env`/`headers` write-only.** Two small, surgical changes that close the two guaranteed data-exposure paths; both have an existing correct pattern in this repo to copy.
4. **H2 — bound and expire `RunEventBus` history.** A ring buffer plus a TTL after the terminal event; without it every long-lived deployment leaks until OOM, and it is a self-contained change to one 40-line class.
5. **H3 — take the LLM judge out of the drain's `FOR UPDATE` transaction.** Restructure to claim → commit → judge → write-back. It is the largest of the five, but it is an explicit spec violation, it holds a pooled connection idle-in-transaction for minutes, and it gets harder to change the longer the surrounding decision plane grows.
