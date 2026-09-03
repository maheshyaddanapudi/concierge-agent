# SSE Event Stream Contract

The chat/run event stream is how the frontend renders a live run: plan cards, route lines, dispatch rails, token streaming, HITL approval cards, and the final answer UI. This document is the contract implemented by `backend/app/orchestrator/recorder.py`, `backend/app/orchestrator/runner.py`, `backend/app/orchestrator/graph_mode.py`, `backend/app/orchestrator/ladder.py`, and `backend/app/api/chat.py`, and consumed by `frontend/src/api/client.ts` (`streamRun`) and `frontend/src/pages/ChatPage.tsx`.

Related: [REST API](rest-api.md) (how runs are started and controlled) · [Workflow DSL](workflow-dsl.md) (where HITL gates come from).

## Connecting

```
GET /api/v1/chat/stream/{run_id}        Accept: text/event-stream
```

- 404 if the run does not exist.
- Each SSE message uses the event's `type` as the SSE **event name**, the event's sequence number as the SSE **`id:`** line (M53), and a JSON **envelope** as data:

  ```
  id: 12
  event: token
  data: {"type": "token", "seq": 12, "run_id": "<uuid>", "ts": "<ISO-8601 UTC>", "payload": { ... }}
  ```

  `seq` is a monotonic per-run counter assigned when the event is emitted (`RunEventBus.emit`); it is the same number as the `id:` line. The frontend registers one listener per known event name on an `EventSource` (`frontend/src/api/client.ts`).
- **Resuming** (M53): `EventSource` sends `Last-Event-ID` on every automatic reconnect; the server replays only events with `seq` greater than it. Clients that cannot set headers pass `?after=<seq>` instead. `Last-Event-ID: 0` (or none) replays everything.

### Replay, reconnect, and stream end

- **Replay**: on connect, the server replays the run's history **after the client's `Last-Event-ID`** (all of it on a first connect), then switches to live delivery (`RunEventBus.subscribe(run_id, after)`, `backend/app/orchestrator/context.py`).
- **Idempotent folding** (M53): the client keeps the highest `seq` it has folded and drops any event at or below it (`streamRun`, `frontend/src/api/client.ts`). A reconnect that overlaps history, or a duplicated event, therefore never re-applies a `token` — this is what keeps answer text from doubling across a reconnect or a deploy. Events without `seq` (none since M53) are folded as they arrive.
- History is **in-memory, per process** and bounded (M51: finished runs are evicted after 15 min, at most 500 runs). **When the process holds no history for a run** (a deploy, a restart, an eviction) and the run's row is terminal or paused, the server **synthesizes the terminal events from the row** (M53): `run_status` + `done` carrying the recorded answer for a completed run, `error` + `run_status: failed` for a failed one, `run_status: cancelled` or `run_status: paused_hitl` otherwise — each with `"replayed_from": "record"` in the envelope and `seq` continuing from the client's `Last-Event-ID`, so folding stays idempotent. A run that is still running elsewhere (another process) opens an empty live stream that heartbeats until its events arrive or it is reaped.
- **Stream end**: the server closes the stream after a terminal event — a `done` event, or a `run_status` with status `failed` or `cancelled` (`_is_terminal`, `backend/app/api/chat.py`). `run_status: completed` is always followed by `done`, so `done` is the practical end-of-stream marker for successful runs. A client that is already caught up on a finished run (`Last-Event-ID` at or past the last event) gets an empty stream that closes at once.
- **`paused_hitl` is not terminal**: the stream stays open across an HITL pause; resume events arrive on the same connection.
- **Heartbeat** (M53): after 15 s with no events the server emits a `ping` event with data `{}` (not enveloped, no `id:`) and keeps waiting — inside the tightest idle timeout a load balancer applies by default. sse-starlette additionally sends a comment line every 60 s as a backstop.
- **Polite close while draining** (M53): once the process is draining (`SIGUSR1`, or the M51 shutdown), a stream on a run this process is **not** executing (a paused run, a run owned elsewhere) receives `event: reconnect` with data `{"reason": "draining", "retry_after_ms": 5000}` and an SSE `retry: 5000` line, then closes. A stream on a run this process **is** executing keeps streaming to its terminal event. `EventSource` reconnects on its own after the retry interval with `Last-Event-ID`; the client does nothing on `reconnect`.
- On `SIGTERM` (the M51 drain), sse-starlette ends every open stream immediately; clients reconnect to the next process and resolve from the record (above). Together with the sequence ids this is the property the M53 deploy evidence records: zero duplicated answer text across a rolling deploy.
- `EventSource` auto-reconnects on network errors; with `Last-Event-ID` and idempotent folding a reconnect costs the client nothing.
- **What `EventSource` does not do** (M53, found by the browser drill): after an **HTTP error** — the frontend proxy's 502 while the backend container is being recreated, a 503 from a balancer — the browser marks the source `CLOSED` and never retries, and a fresh `EventSource` carries no `Last-Event-ID`. `streamRun` therefore reopens the stream itself from the last sequence it folded (`?after=<seq>`), after the last `reconnect` hint's delay (5 s by default), up to `STREAM_REOPEN_LIMIT` (36) attempts — about three minutes, longer than a `deploy.sh` roll with the M51 drain window — and then surfaces an `error` event ("stream lost") rather than leaving the run "running" forever.

## Event catalog

Every event type actually emitted by the backend (grep: `recorder.emit(` / `ctx.recorder.emit(`), cross-checked against the listener list in `frontend/src/api/client.ts`.

### `run_status`

Run lifecycle transitions. Emitted at start (`running`), on pause (`paused_hitl`), on each resume (`running` again), and at the end (`completed` / `failed` / `cancelled`). Source: `backend/app/orchestrator/runner.py`.

| Field | Type | Meaning |
|---|---|---|
| `status` | string | `running` \| `paused_hitl` \| `completed` \| `failed` \| `cancelled` |

### `plan`

The orchestrator's plan. Graph mode emits it once after the planner step; agentic mode re-emits it every time the middleware todo list changes (updates supersede — render only the latest).

| Field | Type | Meaning |
|---|---|---|
| `entries` | array | Graph mode only: `[{id, capability: {type, id?, skill_ids?}, task, depends_on: [id]}]` |
| `todos` | array | Agentic mode only: `[{content, status}]` (`status`: `pending`/`in_progress`/`completed`) |
| `mode` | string | `"graph"` or `"agentic"` |

### `route`

One deterministic ladder resolution (spec §7.1). Emitted per plan entry in graph mode, and when the full-catalog fallback engages. Source: `RunRecorder.record_route` and `fallback_node`.

| Field | Type | Meaning |
|---|---|---|
| `capability` | object | The plan entry's capability, e.g. `{type: "direct_skill", id: "<uuid>"}`; `{type: "full_catalog"}` for fallback |
| `rung` | string | `direct_tool` \| `direct_skill` \| `native_sub_agent` \| `custom_sub_agent` \| `dynamic_worker` \| `fallback` |
| `resolved_to` | object | `{rung, entity_id, entity_name, tier, kind}` (`Resolution.as_route`, `backend/app/orchestrator/ladder.py`); fallback uses `{entity_id: null, entity_name: "full-catalog fallback"}` |

### `dispatch_start` / `dispatch_end`

Brackets around a dispatched unit of work (a sub-agent worker, ephemeral worker, direct tool/skill execution, or the fallback loop). Emitted by `RunRecorder.start_step`/`finish_step` when called with `emit_dispatch=True`. The frontend renders one "rail" per `dispatch_start` and nests child steps under it.

| Field | Type | Meaning |
|---|---|---|
| `step_id` | string | The dispatch step's `run_steps` id — correlates start/end and parents `activity`/`hitl_request` events |
| `tier` | string | Label tier, e.g. `sub_agent`, `tool`, `skill`, `orchestrator` |
| `kind` | string \| null | `native` \| `custom` \| `dynamic` \| `mcp` \| `fallback` … |
| `entity_id` | string \| null | Registry id of the dispatched entity (null for ephemeral workers) |
| `entity_name` | string | Display name (ephemeral workers: `worker-alpha (web-research+file-ops)`) |
| `status` | string | **`dispatch_end` only**: `completed` \| `failed` \| `cancelled` |

### `activity`

The live step ticker: every run-step transition, without payloads. Emitted on every `start_step` (status `running`, full identity) and every `finish_step` (status only). `step_type` values: `plan`, `route`, `skill`, `hitl`, `tool_call`, `aggregate`.

| Field | Type | Meaning |
|---|---|---|
| `step_id` | string | Run-step id |
| `parent_step_id` | string \| null | **Start only.** Owning dispatch step — lets the client nest child lines under the right rail |
| `step_type` | string | **Start only.** See list above |
| `tier` | string | **Start only.** |
| `kind` | string \| null | **Start only.** |
| `entity_name` | string \| null | **Start only.** Skill/tool/agent display name |
| `node_id` | string \| null | **Start only.** Workflow node id, when inside a sub-agent DAG |
| `status` | string | `running` on start; `completed`/`failed`/`cancelled` on finish |

### `token`

A streamed chunk of the final answer text (aggregator streaming in graph mode; the whole final answer as one chunk in agentic mode and for planner `direct_answer`s). Concatenate in arrival order.

| Field | Type | Meaning |
|---|---|---|
| `text` | string | Text delta |

### `thinking`

Model reasoning deltas from the aggregator stream (emitted only when the provider surfaces thinking content). Rendered as a collapsible "model thinking" block.

| Field | Type | Meaning |
|---|---|---|
| `text` | string | Thinking delta |

### `hitl_request`

A human gate is waiting. Emitted by the worker executor just before the run pauses (`backend/app/orchestrator/ladder.py`), and re-announced by the runner after a resume that pauses again on a *different* gate (`_emit_pending_hitl`, `backend/app/orchestrator/runner.py`). Resolve it with `POST /api/v1/runs/{run_id}/hitl` ([rest-api.md](rest-api.md)); a `run_status: paused_hitl` follows shortly after.

| Field | Type | Meaning |
|---|---|---|
| `prompt` | string | The gate's question, from the workflow `hitl` node |
| `node_id` | string | The workflow node id of the gate |
| `questions` | array \| null | Form gate only: `[{id, prompt?, kind: "approve"\|"choice"\|"text", options?}]` — see [workflow-dsl.md](workflow-dsl.md). Present on the original emission; runner re-announcements carry `prompt`/`node_id`/`step_id` only |
| `step_id` | string \| null | The owning **dispatch** step id — the client nests the approval card inside that rail; `null` for ownerless gates |

### `answer_ui`

The formatter's structured artifact, generated after a successful run when `formatter_enabled` is on (`backend/app/orchestrator/answer_ui.py`). The payload carries `presentation` ('a2ui_first'|'raw_first', frozen at run time) and `coverage` (deterministic content-retention percent). Failure-safe: absent whenever generation fails or produces nothing — the streamed `token` text is always the source of truth, and with no artifact the UI shows no structured toggle at all. A separate `charts {charts: [..]}` event carries chart specs produced by the `render_chart` tool during the run — emitted whenever present, independent of the formatter.

| Field | Type | Meaning |
|---|---|---|
| `a2ui` | array | Two A2UI **v0.9** protocol messages: `createSurface` (surface `"answer"`, basic catalog) + `updateComponents` with the flattened component list |
| `charts` | array (optional) | Only when `answer_ui_charts_enabled` and the model emitted chart components: `[{kind: "bar"\|"line"\|"pie", title, labels: [string], series: [{name, values: [number]}]}]` — rendered by the app's own themed SVG chart, not A2UI |

The same payload persists on the run as `answer_ui` and is returned by `GET /conversations/{id}` and `GET /runs/{id}` for reloads.

### `error`

A failure surface. Two shapes from two sources:

| Field | Type | Meaning |
|---|---|---|
| `message` | string | Human-readable error |
| `step_id` | string | Present only for step-level failures (`finish_step(status="failed")`); absent on run-level failure (emitted just before `run_status: failed`) |

### `done`

Terminal success marker; the server closes the stream after sending it.

| Field | Type | Meaning |
|---|---|---|
| `answer` | string | The complete final answer |
| `tokens` | object | `{input_tokens, output_tokens}` run totals |

### `ping`

Heartbeat after 15 s of silence (M53; was 120 s). On the chat stream the data is literal `{}` — no envelope, no `id:`. On the ambient stream (`GET /ambient/stream`, M54) the data is `{"replica": "<replica_id>"}` and every `delivery` event also carries `replica`: behind a balancer a subscriber can tell which process serves it (the §14q-92 drill uses exactly this). Ignore it otherwise.

### `reconnect`

M53. Sent once, then the stream closes: the process is draining and cannot serve this run. Data: `{"reason": "draining", "retry_after_ms": 5000}`; the message also carries `retry: 5000`. Do nothing — `EventSource` reconnects with `Last-Event-ID` after the interval.

## Ordering guarantees

- Events are emitted into a per-run FIFO (`RunEventBus`); subscribers receive history then live events **in emission order**. There is no cross-run ordering.
- A run always begins with `run_status: running`. `plan` precedes `route`; each `route` precedes its entry's `dispatch_start`; `dispatch_end` follows all of that dispatch's child `activity` events.
- `hitl_request` always precedes its `run_status: paused_hitl`. After `POST /hitl`, the next events are `run_status: running`, then either further progress or (multi-gate runs) another `hitl_request` + `run_status: paused_hitl`.
- On success the tail is: [`answer_ui`] → `run_status: completed` → `done`. On failure: `error` → `run_status: failed`. On cancel: `run_status: cancelled` (no `error`).

## Client guidance

- **Fold by sequence, at most once.** Keep the highest `seq` folded and drop anything at or below it (`streamRun` does this for you). `LiveRun` in `frontend/src/pages/ChatPage.tsx` still resets derived state when it attaches to a *different* run id; within one subscription the sequence guard makes reconnects and overlapping replays idempotent.
- **Expect the record after a deploy.** A reconnect that lands on a fresh process may receive `run_status` + `done` with `"replayed_from": "record"` and no intermediate events — render the `done.answer` as the final answer (the conversation reload shows the same text).
- **Reopen after an HTTP error yourself.** A non-browser client should mirror `streamRun`: on a dropped connection let the transport retry with `Last-Event-ID`; on an HTTP error (502/503 during a roll) open a new stream with `?after=<last folded seq>` after the hinted delay, and give up loudly after a bounded number of attempts.
- **Latest-wins events**: render only the newest `plan` (agentic todo updates supersede) and the newest `hitl_request`.
- **The paused_hitl → resolution → run_status pattern (stale-card fix)**: a gate can be resolved from surfaces other than your card — the Settings HITL queue (`GET /hitl/pending`), a cancel, or a resume replay. Never leave an armed approval card based only on your own click. The rule implemented in `ChatPage.tsx` (and verified by `docs/acceptance/22-hitl-stale-card-fix/`): **any `run_status` event arriving *after* the newest `hitl_request` whose status is not `paused_hitl` means that gate has been consumed** — collapse the card to its resolved state. Additionally, a 409 from `POST /runs/{run_id}/hitl` means the run is no longer paused: treat the gate as consumed rather than showing an error.
- **Correlate by `step_id`**: `activity.parent_step_id` and `hitl_request.step_id` point at a `dispatch_start.step_id`, letting you nest child steps and approval cards under the dispatch rail that owns them.
