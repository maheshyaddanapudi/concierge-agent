# Acceptance Evidence — One-Shot Manual UI Campaign

**Date**: 2026-08-06 · **Model**: genuine `anthropic:claude-sonnet-5` (default effort `medium`, planner effort `high`, both configured through the Settings UI) · **Method**: one single, unbroken pass driving the real UI in Chromium against a fresh `docker compose up` (empty database, seeds only). Every button click, form fill, toggle, approval, and denial happened in the browser; the API was used only to *verify* what the UI did (e.g. reading a run's route rungs after the trace screenshot). All 125 screenshots come from this one pass — no evidence is stitched across fixes or retests. Chat panes and trace drawers are captured scrolled top **and** bottom.

Prompt discipline: chat prompts never name a capability, skill, tool, or sub agent. The orchestrator routes on its own judgment; the trials verify what it chose after the fact.

## Stage index

| Folder | What it proves | Spec |
|---|---|---|
| `00-fresh-slate/` | Seeds on a fresh DB: 2 MCP servers, static-badged tools, 2 skills, `research-concierge`, native tool; empty Runs | §9, §14.1 |
| `01-settings-models/` | Providers panel (anthropic configured, google/openai unconfigured), Sonnet 5 + params via UI | §8.7, §2.1 |
| `02-mcp-servers/` | Register form (stdio + http fields), test-connection preview, active status, refresh tools, reconnect | §8.1, §14.2 |
| `03-tools/` | Table + badges, search, source filter, schema drawer, expose toggle → `direct` badge | §8.2, §14.4 |
| `04-skills/` | Bad `{tool:}` mention rejected; editor + preview; exposed skill; **overlap judge flagged the deliberate near-duplicate → cancelled**; edit/version bump | §8.3, §4, §14.3 |
| `05-sub-agents/` | Static seed card (read-only), template picker, **invalid DAG rejected inline → fixed → saved**, skill badges, delete, **delete blocked 409 by dependents**, test-invoke | §8.4, §14.5 |
| `06-trial-graph-thinking-on/` | Trial T1 + plan card + ticker + thinking + gate card + trace; **multi-turn follow-up using history** | §7.1, §8.5, §14.6 |
| `07-trial-graph-thinking-off/` | Trial T2 (same assertions, thinking off, anthropic theme) | §7.1 |
| `08-trial-agentic-thinking-on/` | Trial T3 + live todos + gates + trace; **mid-conversation tool exposure used live in the same session** | §7.2, §14.11 |
| `09-trial-agentic-thinking-off/` | Trial T4 (google theme) | §7.2 |
| `10-fallback-uncovered-ask/` | Uncovered ask → planner no-confident-match → **full-catalog fallback rung** in trace | §7.0, §8.5, §14.7 |
| `11-hitl-deny-and-queue/` | **Deny** with note + denied outcome; second paused run resolved from the **Settings HITL queue** | §8.5, §8.7 |
| `12-stop-and-queued-message/` | Send→Stop mid-run → cancelled; **queued draft auto-fires** after the run ends | §8.5 |
| `13-failure-retry-cancel/` | MCP deactivate → run degrades via error branch → reactivate + reconnect-all; **fallbacks disabled via UI → genuine failed run with clear message → re-enable → Retry (re-plan) → completed**; cancel + delete from Runs page | §8.6, §14.8–9 |
| `14-runs-and-ops/` | Runs table with mode badges, search; log level, exposure-cap banners on Tools & Skills, seed reload | §8.6, §8.7, §10 |
| `15-static-guards/` | Static skill/server/tool drawers: definition fields disabled, no delete, status toggles live | §4, §8 |
| `16-theme-gallery/` | The same conversation in all four themes; picker restored to default | §8.7 |
| `17-data-purge/` | Purge run history with confirm → empty Runs | §8.7 |

`campaign.log` is the pass's full console log, including the per-trial routing verification lines.

## The routing matrix (the campaign's centerpiece)

One neutral four-part prompt (file gist · web research saved to workspace · notes reformatting · directory listing), zero capability vocabulary, across all four mode × thinking combinations:

| Trial | Mode | Thinking | Sub agents dispatched | Direct skill | Direct tool | HITL gates | Fallback | Status |
|---|---|---|---|---|---|---|---|---|
| T1 | graph | on (med/high) | site-analyst, research-concierge | notes-formatter | sitefiles.list_directory | 1 approved | none | completed |
| T2 | graph | off | site-analyst, research-concierge | notes-formatter | sitefiles.list_directory | 2 approved | none | completed |
| T3 | agentic | on (med/high) | site-analyst, research-concierge | notes-formatter | sitefiles.list_directory (loop tool call) | 2 approved | none | completed |
| T4 | agentic | off | research-concierge, site-analyst | notes-formatter | sitefiles.list_directory (loop tool call) | 2 approved | none | completed |

Every trial produced **two different sub agents + a direct skill call + a direct tool call**, chosen by the orchestrator alone, with zero fallbacks — a fully clean matrix. The research part fetched the live web (sources cited) and wrote the findings to a `/workspace` file.

## Acceptance script (spec §14) mapping

1. Seeds visible → `00-fresh-slate/` ✅
2. Register stdio server, tools ingest → `02-mcp-servers/`, `03-tools/` ✅
3. Create skill, badges on both pages → `04-skills/` ✅
4. Expose a tool, rung-1 route in next trace → `03-tools/` + T1 trace (`direct_tool` rung) ✅
5. Sub agent with branch + HITL; validation error rejected inline, fixed, saved → `05-sub-agents/` ✅
6. Multi-turn: message 1 invokes the new sub agent with HITL approve; message 2 follows up via history → `06-trial-graph-thinking-on/` ✅
7. Uncovered ask → no confident match → **full-catalog fallback rung** in the trace (§14.7 as amended to match §7.2) → `10-fallback-uncovered-ask/` ✅
8. Server down → error path → run completes via error branch; server status visible; reconnect from Settings → `13-failure-retry-cancel/` ✅
9. Full trace with nested steps/tokens/route reasons; cancel a running run; retry a failed one → trial traces + `13-failure-retry-cancel/` ✅
10. Model change reflected (Sonnet 5 set via UI, visible in trace labels); HITL queue; purge → `01`, `11`, `17` ✅ (second-provider switch N/A: only the Anthropic key is configured; providers panel in `01` shows google/openai unconfigured)
11. Agentic mode repeat with todos + same sub agent as dispatch tool + HITL + comparable trace; mid-loop MCP tool plug-in callable in the same session → `08-trial-agentic-thinking-on/` ✅

## Graph vs agentic — what the traces show

Same registries, same ladder policy, same recording labels; different orchestration:

- **Planning**: graph mode runs a dedicated planner call producing a validated plan artifact (the plan card in T1/T2 shows entries and waves; invalid ids would be repaired or fail cleanly). Agentic mode plans emergently — the todo list streams and re-writes itself as the loop learns (T3/T4 todo shots).
- **Capability access**: graph mode resolves each plan entry through the pure-code ladder (`route` steps show the rung chosen and why). Agentic mode receives capabilities *as tools* — the three registry middlewares project the live registries into every model call, and each invocation is still logged as a route-equivalent step, which is why the traces stay comparable.
- **Parallelism**: graph mode dispatches independent plan entries concurrently (`Send`); agentic mode is sequential except for parallel tool calls within a single turn.
- **Failure posture**: graph mode fails a run when the plan can't validate/resolve (see the forced failure in `13`); the agentic loop self-corrects — tool errors come back as messages, with `use_full_catalog` escalation and `spin_worker` (strict UUID contract, corrective feedback) as traced fallbacks.
- **HITL**: identical interrupt/resume machinery — the same approval card pauses either mode.

## Bugs found by this campaign cycle (all fixed, tested, committed before the final pass)

1. `spin_worker` crashed whole runs on model-given non-UUID skill ids → strict UUID contract + corrective tool feedback + registry ids printed in the skills catalog (`5136239`).
2. `PATCH /mcp-servers/{id}` 500 (`MissingGreenlet` on flush-expired `updated_at`) → post-commit refresh (`ba5d27a`).
3. Structlog never rendered tracebacks (`format_exc_info` missing) (`a70c467`).
4. A dead MCP server raised through the tool proxy and killed agentic runs → contained as an error `ToolMessage` (strict skill loops keep error-edge semantics) (`768cc4e`).
5. `summarize-and-structure` structured output occasionally failed schema validation (non-array fields) → one planner-style repair retry (`2d8559e`).
6. Theme polish surfaced by evidence review: the toggle knob rode the button's default padding and drifted outside its track (invisible white-on-white in light themes), and the a2ui answer cards stayed dark on light themes because the global `color-scheme: dark` forced their `light-dark()` styling — fixed with an explicit knob anchor + visibility ring and per-theme `color-scheme` (`4c66119`); this evidence set is captured on the fixed build.

## Post-campaign refresh (user-directed)

Two screenshots were re-captured manually through the UI on build `d9bbe98`
after chat-presentation review; the rest of the set is the original single
pass:

- `08-trial-agentic-thinking-on/05-t3-hitl-gate-1.png` — dispatch rails now
  show the running entity's NAME on every tier (`SUB_AGENT · CUSTOM ·
  site-analyst`, `SKILL · CUSTOM · notes-formatter`), from the same
  reproduced scenario (agentic + thinking on, BIG prompt, first gate).
- `13-failure-retry-cancel/11-retried-run-conversation-bottom.png` — reloaded
  history now interleaves correctly: the failed run shows its ✕ error bubble
  (matching the live view) between the original prompt and the retry, and the
  A2UI panel is captioned "answer panel · structured view" so it reads as a
  companion to the text answer rather than a duplicate response.

## Observations

- Spec §14 step 7 was amended (`e9cac23`) to match §7.2: a no-confident-match engages the full-catalog fallback rather than force-spinning a worker (unexposed skills are invisible to the planner by design); rung-4 dynamic workers stay reachable via `spin_worker` and covered per-rung by the API test suite.
- The fallback banner renders during live runs (route rails are a live-stream affordance; reloaded conversations show answers, with routing detail in the trace — where rung `fallback` is recorded, satisfying §7.0's tracing invariant).
