# Acceptance campaign — A2A wave (`docs/acceptance/`)

Full 1:1 re-run of the [ambient acceptance campaign](./report-ambient.md)
— every stage, every frame name — **plus stage 27, the A2A wave (spec §19,
§14d steps 33–40)**. Captured end-to-end in the **anthropic theme** on live
**`openrouter:qwen/qwen3.8-max`** (all roles unless a stage tests another
provider), against a fresh stack: `./decom.sh -y` (fresh volumes), rebuilt
images with the a2a-sdk/authlib dependencies, seeds from scratch.

**Verdict: pass.** All 27 base stages at exact frame parity with the ambient
campaign, both feature sweeps green, and the eight §14d A2A steps proven
live. Two real product defects were found by this campaign and fixed on the
branch with regression tests (details below) — exactly what a live re-run is
for.

## Layout

| Stage | What it proves |
|---|---|
| `00`–`05` | Fresh slate, settings/models (qwen3.8-max default), MCP registration, tools, skill authoring + bad-mention rejection, sub-agent builder + overlap judge + DAG preview |
| `06`–`09` | Four full HITL research trials: graph/agentic × thinking on/off — plan card, rails, gate, resume, A2UI answer, follow-up turn, trace |
| `10`–`12` | Full-catalog fallback on an uncovered ask; HITL deny + approval queue; Stop + queued message |
| `13` | Failure/retry/cancel. Frames `00/01/03` fresh; **frames `04`–`08` carried over from the ambient campaign** (visibly default-theme) — see Honest notes |
| `14`–`18` | Runs/ops, static guards, four-theme gallery, data purge, registry cache + retrieval |
| `19`–`20` | Provider-agnostic on `openai:gpt-5.6-terra`; heterogeneous role mix (sonnet-4-6 default · terra planner · gemini-3.6-flash aggregator) |
| `21`–`24` | M8 form gates + charts, stale-HITL-card cross-tab fix, ops fixes, formatter on/off |
| `25` | Memory §16 lifecycle: quick-add, chat-taught fact + quarantined instruction, extraction, review, supersede, pin, cross-conversation recall, hard delete |
| `26` | Ambient §17/§18 lifecycle: typed routine builder, real webhook fire, ledger chain + precision, watch compile (NL + typed), digest delivery to live SMTP/webhook sinks, feedback, evals page |
| `27-a2a` | The A2A wave — below |

## Stage 27 — A2A (spec §14d steps 33–40)

Counterparties: the same scripted SDK-server stub the contract tests use
(`backend/tests/a2a_counterparty.py`), run as host processes on the docker
bridge — no new compose service. Four of them: `polyglot-agent` (bearer,
translate/glossary), `keyed-notary` (apiKey header), `oauth-archivist`
(oauth2 client_credentials), `mtls-vault` (mutualTLS only — unsupported by
design).

| Frames | Step | Proof |
|---|---|---|
| `00`–`02` | §14d-33 | Dark: Remote Agents nav absent, `POST /remote-agents` → **409**; enable → nav appears |
| `03`–`05` | §14d-34 | Registered by card URL from the page; card renders, skills list, bearer scheme visible |
| `06`–`07` | §19.3 | Write-only credentials: password inputs, save → `auth_status: ok`. The API response's key list was machine-checked — **`credentials` is never serialized** |
| `08`–`09` | §14d-34 | Both card skills projected as `kind=a2a` tools (`polyglot-agent.translate`, `.glossary`) with the agent-prefixed key |
| `10`–`13` | §14d-36 | `document-translation` skill authored in the UI over the a2a tool ({tool:…} mention), ExComm delegate sub agent over the skill |
| `14`–`17` | §14d-36 | **Organic routing**: the chat prompt ("Our Montreal customers need this release note in French: …") names no skill/agent/tool — the planner picked `document-translation` (capability id matched in the stored plan). Remote answer lands **inside `<untrusted_remote_agent_output>`** in the trace (machine-verified in step outputs) |
| `18`–`20` | §14d-37 | Remote `input-required` → the standard HITL card carrying the question marked *untrusted, its own words*; typed reply ("European French (fr-FR)…") resumes the same remote task to completion |
| `21`–`22` | §14d-37 | Deny with a note → remote task cancelled — the counterparty recorded `tasks/cancel` (0→1) |
| `23`–`24` | §14d-38 | Stop mid-call → run cancelled AND `tasks/cancel` reached the counterparty (1→2) |
| `25`–`28` | §14d-39 | 20s budget → task **parked** with the honest tool note; run completed with **no recheck run**; ambient leader tick polled the finished remote task; fenced result delivered to the Inbox as `category=a2a`; drawer row flipped to delivered |
| `29`–`31` | §14d-39/40 | Parked-then-ask: tier-1 "needs your input" delivery; reply typed in the Remote Agents task drawer; remote task completed |
| `32`–`33` | §14d-40 | Card drift: counterparty added `proofread` live; Refresh card projected the new `kind=a2a` tool |
| `34`–`39` | §14d-35 | Auth matrix: apiKey resolved from **`env:STUB_A2A_KEY`** (auth ok chip + authenticated echo round-trip), oauth2 client_credentials (**exactly one token minted** at the stub's `/token`, then an authenticated echo round-trip), mutualTLS-only card → `auth-unsupported` chip; the call sends no credentials (nothing supported to place) and fails as a clean `401 Unauthorized` tool step, with the run completing and reporting it honestly |

## Defects found by this campaign (fixed on the branch)

1. **Inline skill loop swallowed GraphInterrupt** (`run_inline_skill`,
   rung-2 `direct_exposure` skills). A remote `input-required` surfaced as a
   raw `Interrupt(...)` repr inside a failed step instead of pausing or
   erroring cleanly. Root cause: the third blanket `except Exception` around
   an interrupt-carrying path — M38 fixed the other two (rung-1 direct tool,
   graph worker nodes); unit tests happened to ride the checkpointed worker
   path where pausing works. Fixed to the rung-1 contract (inline runs have
   no checkpointer, so they *cannot* pause: clear error pointing at the task
   drawer, remote row stays `input-required`) + regression test.
   Commit `fix(orchestrator): inline skill loop must not swallow GraphInterrupt…`
2. **`gpt-4o` removed from the OpenAI list.** OpenAI's `/v1/chat/completions`
   now rejects function tools when reasoning parameters are in play; the
   gpt-5.x entries ride the adapter's Responses-API path (explicit `effort`),
   but gpt-4o has no effort knob and no escape route. Caught when stage 20's
   planner leg 400'd. Commit `fix(llm): drop gpt-4o from the openai model list`.

## Honest notes

- **Stage 13 frames `04`–`08` are copies from the ambient campaign** (user-
  approved). The retry demo needs a *failed* run as a precondition, and the
  fresh stack refused to produce one honestly: off-list model refs 422 at
  save (M33 validation working), and across many attempts qwen either
  completed runs or had the planner decline uncovered asks directly
  (`direct_answer`) rather than reporting `no_confident_match` — the only
  branch that fails a run with the fallback disabled. The prior campaign's
  failure was a naturally occurring provider rate-limit that did not recur.
- **Stage 20's planner is `openai:gpt-5.6-terra` with `effort: low`** (the
  ambient campaign used `gpt-4o`): the explicit effort routes the planner
  through the Responses API, which is now the only way OpenAI accepts
  function tools + reasoning on these models. Provider-side drift, not a
  regression — and live validation of why the adapter grew that path.
- **HITL routing in stage 27** rides the ExComm delegate (checkpointed sub
  agent), not the inline skill rung — inline loops cannot pause by design
  (see defect 1); the skill was left unexposed so organic resolution takes
  the delegate. This is the §7.1 ladder working as specified.
- The stub's forced-ask mode asks on *every* new task; qwen sometimes makes
  a follow-up tool call after an answered question, which would re-ask. The
  campaign drops the forced mode once the demo card resolves — one clean
  round-trip per scenario.
- `form-demo`/`gate-demo` (stage 21/22) and the workspace fixtures were
  recreated on this fresh stack — the ambient campaign inherited them from
  earlier eras' database state.

## Reproduction

Fresh `docker compose up` (with the sandbox proxy override), then the
`camp-a2a/` scripts in session scratch: `campaign-00-01 … campaign-26b`,
`a2a-27a … a2a-27e` with `OUT=docs/acceptance`. Counterparties:
`python -m tests.a2a_counterparty --port 8027|8028|8029|8030 …` from
`backend/` (see the module docstring).
