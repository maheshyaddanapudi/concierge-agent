# Acceptance Demo Script — Execution Report

Every step of the spec §14 Acceptance Demo Script, executed against the docker-compose
stack (`db`, `backend`, `frontend`) with evidence captured in `docs/acceptance/`.
UI steps were driven in a real Chromium browser (Playwright); API steps via `fetch`/curl.

**Model note.** No provider API key was configured in this environment, so every model
decision was produced by the **fake scripted provider** (spec §11) through the same
`ModelProvider` port and `get_model("fake:scripted")` path the real adapters use. The
`/_fake/script` control endpoint (mounted only when `FAKE_LLM_ENABLED=1`) queued each
model turn, which makes the walk deterministic and reproducible. Everything else — MCP
servers and their subprocesses, file reads/writes, Postgres registries, SSE streams,
HITL checkpoints, run traces — is fully real. With `ANTHROPIC_API_KEY` set, steps 4–11
re-run identically with genuine model decisions (and step 10's provider switch becomes
exercisable with a second key).

| # | Step (spec §14) | Result | Evidence (`docs/acceptance/`) |
|---|---|---|---|
| 1 | Fresh `docker compose up` → seeded registries visible in UI | ✅ | `step1a-servers-seeded.png`, `step1b-tools-static-badges.png`, `step1c-research-concierge.png` |
| 2 | Plug a new MCP server (`sitefiles`, stdio) from the UI, no restart → tools ingested with `server.tool` keys | ✅ | `step2a-register-form.png`, `step2b-server-active.png`, `step2c-tools-server-dot-tool-keys.png` |
| 3 | Author a custom skill in the UI binding the new tools | ✅ | `step3a-skill-editor.png`, `step3b-skills-page-badges.png`, `step3c-tools-page-skill-badges.png` |
| 4 | Expose a tool directly → chat routes rung 1 with a real MCP tool call | ✅ | `step4a-expose-toggle.png`, `step4b-direct-badge.png`, `step4c-chat-rung1.png`, `walkA-rerun.log` (real `/tmp` listing in the tool_call step) |
| 5 | Build `site-analyst` sub agent in the workflow builder (branch + error edge + HITL); invalid DAG rejected inline | ✅ | `step5a-builder-with-error-edge.png`, `step5b-validation-rejected-inline.png`, `step5c-site-analyst-saved.png` |
| 6 | Multi-turn chat: dispatch to site-analyst, HITL pause → approve with note → idempotent resume; follow-up uses history; A2UI answer panel | ✅ | `step6a-hitl-card.png`, `step6b-completed-after-approve.png`, `step6c-followup-history-a2ui.png`, `walkA-rerun.log` (1 work step, 1 hitl step after replay) |
| 7 | Request covered by no exposed capability → rung-4 ephemeral dynamic worker (`kind=dynamic`, `entity_id=null`) | ✅ | `step7-ephemeral-worker.png`, `walkA-rerun.log` |
| 8 | Kill the MCP server process → tool failure routes the error edge; health flips to error; reconnect restores active | ✅ | `step8-chat-error-branch.png`, `step8a-server-error-status.png`, `step8b-reconnected-active.png`, `walkB-rerun.log` |
| 9 | Run trace: nested parent-linked tool_call with token usage; HITL queue; cancel a running run; retry a failed run | ✅ | `step9a-hitl-queue.png`, `step9b-trace-nested-native.png`, `step9c-cancelled.png`, `step9d-retried.png`, `runs-dump-pre-purge.json` |
| 10 | Settings command center: planner model + params → next run's plan step carries the model label; purge run history | ✅ | `step10-purged.png`, `walkB-rerun.log` (provider *switch* n/a — single provider configured; the label/params path is proven via the port) |
| 11 | Switch to agentic mode: todos stream as plan events, dispatch tool reaches site-analyst, HITL pause/approve resumes correctly, and an MCP server plugged **mid-conversation** is callable in the same session (middleware live-sync) | ✅ | `step11a-todo-stream.png`, `step11b-agentic-completed.png`, `step11-run.json`, `walkB-rerun.log` |

## Step 11 trace (the full-stack proof)

`step11-run.json` is the completed agentic run. Its step list shows, in order: the
`custom_sub_agent` route → the `agentic:site-analyst` dispatch step (exactly one,
completed — adopted across the HITL pause, not duplicated) → the real `sitefiles`
read of `/tmp/site-notes.txt` → work/hitl/finish nodes with router steps → a
`tool_call` step whose result is the container hostname read via
`extras.read_text_file` — a tool from an MCP server plugged *after* the run had
already paused — → the aggregate step with the final answer.

## Genuine-model verification (ANTHROPIC_API_KEY configured)

After the scripted walk, the LLM-dependent steps were re-run with **real
`anthropic:claude-sonnet-4-6` decisions** — no `/_fake/script` anywhere — driven
through the UI in a real browser (`walkC-genuine.log`, `genuine-01..27.png`):

- **Page tour** — all seven admin pages with the Anthropic provider live through the port (`genuine-01..10`).
- **Rung 1** — the genuine planner routed "list the files in /tmp" to the exposed MCP tool: `rungs=[direct_tool]`, real listing in the trace (`genuine-11..12`).
- **Sub agent + HITL** — the genuine planner dispatched to site-analyst, the worker really read `/tmp/site-notes.txt`, paused at the gate, showed in the Settings HITL queue, was approved with a note, and resumed idempotently: `rungs=[custom_sub_agent]`, one hitl step, one work step (`genuine-13..18`).
- **Conversation history** — the follow-up answer correctly recalled the file just read (`genuine-19`).
- **Agentic mode** — the genuine concierge chose `dispatch_site-analyst` on its own, paused for approval, and the resume replayed the dispatch tool through fresh middleware instances: `dispatch=[agentic:site-analyst:completed]`, `hitl=[approve:completed]` (`genuine-21..26`).
- **Unexposed skill** — asked to "run the notes-formatter skill", the genuine planner escalated to the full catalog and invoked the isolated skill loop (route steps `fallback` → `notes-formatter`). The scripted walk and pytest cover the rung-4 ephemeral-worker ladder path.

The genuine pass also surfaced (and fixed) two defects the fake provider cannot
catch: duplicate registry names produced duplicate bound tool names (a real
provider 400 — now id-suffixed on collision), and stdio MCP subprocesses lost
deployment network env (now passed through). A UI gap found during the browser
walk was fixed too: reopening a conversation now re-attaches to its paused run.

## Determinism verification (genuine model, chat-driven, UI screenshots)

`walkD-determinism.log`, `walkD-results.json`, `walkD2-results.json`, `determinism-*.png`.
Question under test: does the system dispatch a sub agent *without* being told to,
and which layers of the system are deterministic?

**Implicit routing (nobody names the sub agent)** — "Please summarize the file
/tmp/site-notes.txt for me":

- *With a decoy in the registry* (the `extras.read_text_file` tool left exposed from
  the live-sync test, rooted at `/etc`): graph mode picked the exposed tool 3/3 times
  (rung 1 is cheaper than a sub agent), the tool denied the path, and the runs
  completed with honest "could not read" answers. Agentic mode did the same 2/2.
- *Decoy removed* (`determinism-03`): the same prompt dispatched **site-analyst by
  description alone**, 3/3 — graph ×2 and agentic ×1 — each pausing at the HITL gate
  and completing after approval (`determinism-08/09/10 a–e`).
- Conclusion: **yes, sub agents kick off unprompted** — selection is description-driven
  model judgment over the live registry, and the *exposure configuration decides the
  candidate set*. Registry hygiene (what is exposed, how things are described) is the
  steering wheel.

**Repeatability of the constrained path** — "Use the site-analyst sub agent…" ×3:
route identical 3/3 (`custom_sub_agent→site-analyst`), DAG node order identical 3/3
(dispatch → work → gate → finish), HITL exactly once each. Bounded variation stayed
inside the skill loop (the work node called its bound tool once in one run, twice in
the others) and in the answer prose — never in the route, the DAG order, or isolation.

**Deterministic ladder rule** — same skill ask with exposure flipped: exposed →
`direct_skill→summarize-site` (rung 1, no HITL); unexposed → `custom_sub_agent→site-analyst`
(rung 3, HITL gate) (`determinism-06/07`). The rung tracked the registry rule exactly,
not the model's mood.

| Layer | Verdict | Evidence |
|---|---|---|
| Resolution ladder, DAG order, HITL mechanics, tool isolation | Deterministic | batch C ×3 identical, batch D rule flip, 163 pytest |
| Planner/router/skill-loop choices (schema-forced, catalog-bound, call-limited) | Partially deterministic | batch C: same route/path, varying inner tool iterations |
| Capability selection on ambiguous asks, answer prose, todos | Non-deterministic (steerable via exposure/descriptions/params) | batches A/B vs A′/B′ flip after registry change |

## Complete from-scratch retest (UI-driven)

`complete_retest/` re-runs the whole lifecycle on a wiped database, entirely through
the admin UI with genuine model decisions: MCP registration → tool ingest → skill
authoring → sub agent authoring → implicit routing (both modes) → HITL → traces.
It also exercises the **overlap guard** end to end (duplicate skill and duplicate sub
agent both flagged by the LLM judge and cancelled; a legitimate borderline flag
confirmed via "Save anyway"), and proves implicit sub agent selection works with a
**path-free description**. See `complete_retest/README.md` for the shot-by-shot map.

## Multi-capability orchestration (one neutral prompt, no capability vocabulary)

`walkF-multiagent.log`, `walkG-complex.log`, `multi-*.png`. A four-part prompt in
plain user language ("give me the gist of…", "find out from the web and keep what
you learn in a file…", "turn these rough notes into a bullet list", "what's sitting
in /tmp?") with thinking enabled, against a registry offering two HITL-gated sub
agents, an unmapped skill, and an unmapped exposed tool:

- **Graph mode** (`multi-06*`): the planner decomposed unprompted into
  `custom_sub_agent→site-analyst` + `custom_sub_agent→research-concierge` +
  `direct_tool→sitefiles.list_directory`, answered the trivial reformat itself, and
  the run paused at **two parallel HITL gates approved one at a time** before
  aggregating all four answers.
- **Agentic mode** (`multi-05*`): the concierge dispatched both sub agents
  sequentially (two gates, two approvals), called the exposed tool directly for the
  /tmp listing, and inlined the reformat — all four parts answered, ~30 traced tool
  calls including the real web fetch and the workspace file write.
- Neither model delegated the trivial reformat to the unmapped `notes-formatter`
  skill — both rationally inlined it; the rung-4 unmapped-skill path is proven
  separately (explicit ask → fallback → isolated skill loop; plus the scripted
  walk and pytest ladder coverage).

This scenario surfaced and fixed three real orchestration bugs the simpler walks
could not reach: (1) parallel HITL gates erroring on resume (one decision now
answers one live gate and the run re-pauses for the rest, stale interrupts are
skipped, finished workers replay from their recorded results); (2) plans that mix
a `direct_answer` with capability entries silently dropped the entries (both now
execute and merge at aggregation); (3) the seeded `max_tool_iterations` was too
tight for genuine web research with thinking (runtime setting, raised in the demo
stack; the agentic mode's retry → full-catalog escalation recovery worked as
designed while the budget was still tight — `walkF-multiagent.log`).

## Hard-constraint audit

`constraint-audit.txt` (executed greps + counts): exactly three compose services and
no broker/queue/Redis/Celery anywhere; zero provider SDK or LangChain provider-package
imports outside `app/llm/`; all 8 prompts as files under `app/prompts/`; no API key
material in models, settings store, UI, or logs; all four `create_agent` call sites
take their middleware from `build_middleware_stack(...)`; the shared adapter contract
suite passes for every registered adapter (34 tests).

## Test suites

- Backend: `pytest` — 161 passed; `ruff check` + `ruff format --check` clean; `mypy` strict on `app/` clean.
- Frontend: `eslint` — 0 errors; `vitest` — 7 passed; production build clean.

## Reproducing

```bash
docker compose up          # fresh stack; seeds load on first start
# keyless: FAKE_LLM_ENABLED=1 in .env, default model fake:scripted in Settings
# scripted walks: drive the UI per spec §14, or script model turns via POST /api/v1/_fake/script
```
