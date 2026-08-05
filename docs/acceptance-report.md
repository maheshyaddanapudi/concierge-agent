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
