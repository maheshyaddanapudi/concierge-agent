# Acceptance campaign — A2A wave (`docs/acceptance/`)

Full 1:1 re-run of the [ambient acceptance campaign](./report-ambient.md)
— every stage, every frame name — **plus stage 27, the A2A wave (spec §19,
§14d steps 33–40)**. Captured end-to-end in the **anthropic theme** on live
**`openrouter:qwen/qwen3.8-max`** (all roles unless a stage tests another
provider), against a fresh stack: `./decom.sh -y` (fresh volumes), rebuilt
images with the a2a-sdk/authlib dependencies, seeds from scratch.

**Verdict: pass.** All 27 base stages at exact frame parity with the ambient
campaign, both feature sweeps green, and the eight §14d A2A steps proven
live. **Stage 28 (M40 config hardening, §14e steps 41–44) was added on the
`config_hardening` branch** — per-chat pin, settings completeness, wired-knob
behavior, byte-identity — with the affected settings frames surgically
recaptured in place. Four real product defects were found across these
campaigns and fixed on their branches with regression tests (details below)
— exactly what a live re-run is for.

## Layout

| Stage | What it proves |
|---|---|
| `00`–`05` | Fresh slate, settings/models (qwen3.8-max default), MCP registration, tools, skill authoring + bad-mention rejection, sub-agent builder + overlap judge + DAG preview |
| `06`–`09` | Four full HITL research trials: graph/agentic × thinking on/off — plan card, rails, gate, resume, A2UI answer, follow-up turn, trace |
| `10`–`12` | Full-catalog fallback on an uncovered ask; HITL deny + approval queue; Stop + queued message |
| `13` | Failure/retry/cancel — all frames fresh: the failure is a genuine provider-unreachable run (`APIConnectionError`, produced by severing egress at the proxy forwarder), then retry-from-drawer and per-run delete — see Honest notes |
| `14`–`18` | Runs/ops, static guards, four-theme gallery, data purge, registry cache + retrieval |
| `19`–`20` | Provider-agnostic on `openai:gpt-5.6-terra`; heterogeneous role mix (sonnet-4-6 default · terra planner · gemini-3.6-flash aggregator) |
| `21`–`24` | M8 form gates + charts, stale-HITL-card cross-tab fix, ops fixes, formatter on/off |
| `25` | Memory §16 lifecycle: quick-add, chat-taught fact + quarantined instruction, extraction, review, supersede, pin, cross-conversation recall, hard delete |
| `26` | Ambient §17/§18 lifecycle: typed routine builder, real webhook fire, ledger chain + precision, watch compile (NL + typed), digest delivery to live SMTP/webhook sinks, feedback, evals page |
| `27-a2a` | The A2A wave — below |
| `28-config-hardening` | M40 (spec §14e steps 41–44) — below |
| `29-ambient-pursuit` | M41 (spec §14f steps 45–47) — below |

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

## Stage 28 — Config hardening (spec §14e steps 41–44, M40)

Captured on the same fresh stack (rebuilt M40 images, qwen3.8-max all
roles, anthropic theme), with the polyglot counterparty back on the
bridge for the poll-interval proof.

| Frames | Step | Proof |
|---|---|---|
| `00`–`06` | §14e-41 | **Per-chat pin**: research-concierge pinned in conversation A (badge + `mode='direct'` run); new conversation B opens at Orchestrator (auto) — machine-checked empty picker — and runs planner-routed (`graph`); back in A the pin **and** the history-summary checkbox are restored, and the next message runs direct with `+ctx`. The API run list closes the loop: A's runs `direct`, B's `graph` |
| `07`–`14` | §14e-42 | **Settings completeness**: Ambient master toggled ON from the page → the Ambient nav entry appears live, every §17 knob + §18.4 channel routing renders; tick interval PATCHed to 45 and read back after reload; tick=5 → the **422 detail renders inline under the control**; A2A master ON → Remote Agents nav appears + all six §19 knobs (max-parked shows the "0 disables parking" hint); the always-visible API-guardrails pair; Orchestrator's new overlap-threshold + recursion-limit knobs |
| `15`–`18` | §14e-43 | **Poll interval is tick-bounded**: tick 15s, task budget 2s, `a2a_poll_interval_s=3600` → a parked remote task stays parked across 40s (>2 ticks, machine-checked: no recheck, no delivery); PATCH the interval to 1 → the next tick settles it and the fenced result lands in the Inbox |
| `19`–`20` | §14e-43 | **Overlap threshold is live**: at `overlap_threshold_percent=10`, a loose cousin of `web-research` ("web-brief-writer") raises the §4 dialog on save — judged 85%, threshold 10 shown in the dialog — cancelled, registry unchanged |
| `21`–`22` | §14e-43 | **Rate-limit boundary moves**: guardrails section at burst 5; then with `AUTH_ENABLED=1`, the curl transcript shows 429 from request 5 of 8 at `burst=5/refill=1`, and 8×200 after PATCHing back to `120/10` |
| `23`–`24` | §18.4 | **In-app ambient toast, live**: Runs page held open (ambient on, tick 15s, outside quiet hours), a tier-0 delivery inserted **server-side** — no click, no navigation — then the tick's flush dispatched it as an interrupt, `/ambient/stream` broadcast it, and the toast rendered bottom-right ("AMBIENT INTERRUPT · OPS — TOAST PROOF (M40) …"). **No reload**: a `window` marker planted before the insert was still present after the toast appeared (a navigation would have cleared it), and the delivery row reads `{tier: 0, channel: "interrupt", delivered: true}` |
| — | §14e-44 | **Byte-identity at defaults**: fresh boot on the rebuilt images shows every M40 key at exactly the constant it replaced; the full backend suite (735 passed, 1 skipped) runs on those defaults untouched |

The toast was added here because it was the one ambient surface with no
anthropic-theme frame — its only prior runtime proof is
`ambient_channels_m29/02-toast-visible.png` (M29, default theme, preserved
as an archive) — and because it sits one step downstream of a knob M40
changed: the delivery flush that broadcasts it rides the now-configurable
ambient tick. Stage 28c's own A2A delivery could never have exercised it
(completed remote tasks deliver at tier 2, and the toaster drops
`tier > 1` to the inbox by design), so the broadcast path was re-proven
directly.

## Stage 29 — Ambient pursuit (spec §14f steps 45–47, M41)

Channel routing was presence-blind: a configured `email` on `interrupt`
sent whether or not the toast had already landed in front of you.
`ambient_pursuit` gates the external half of the dispatch on whether the
in-app half reached anyone, with the SSE subscriber set — the literal
audience of the toast just sent — as the oracle.

Run on the rebuilt M41 images against **live sinks**: the M29 local SMTP
sink on `:8025` and the SMS-gateway-shaped webhook sink on `:8026`, both
reached over the compose bridge, with `ambient_channels` routing
`interrupt` to `["in_app", "email", "webhook"]`. Every scenario inserts a
tier-0 delivery server-side and lets **the app's own ambient tick** flush
it — the flush must happen inside the running process, since that is where
the SSE subscribers live and therefore the only place the toast and the
oracle both see reality.

| Frames | Step | Proof |
|---|---|---|
| `00` | §8.7 | The pursuit select rendered beside the channel routing it modifies, with its subordination hint |
| `01` | §14f-45 | **away + watching**: browser holding the stream, tier-0 flushes → toast fires and the external channels are **held** — machine-checked: SMTP sink +0, webhook sink +0, `external` ledger `null` |
| `03` | §14f-46 | **away + nobody watching**: browser closed, 25s for the stream to unregister, same tier-0 → **both sinks receive**. The transcript quotes what actually landed: the SMTP message (`Subject: [concierge] ambient interrupt: 1 item(s)`) and the webhook envelope (`{"kind":"ambient_delivery","mode":"interrupt","items":[…]}`), with `external` recording `ok:true` per channel |
| `03` | §14f-47a | **Quiet hours beat pursuit**: with quiet hours spanning the current hour, the same tier-0 is demoted to tier 2, `delivered_at` stays null, and **neither** a toast nor an external send occurs — pursuit escalates the channel, never the hour |
| `03` | §14f-47b | **`off` + nobody watching**: delivered in-app, nothing external, ledger empty |
| `02`, `03` | §14f-47c | **`always` + watching**: external fires anyway — the pre-M41 byte-identity leg — and the Inbox shows the pursued deliveries |

All five scenarios passed in one run (`5/5` in the transcript). Two honest
notes: the notification budget was raised to 20 for the stage so five
interrupts fit in one day (budget behavior itself is proven by §14c-26 and
the M41 unit suite), and the deliveries were synthetic tier-0 `ops` rows
inserted server-side rather than driven from a natural producer — the
dispatch path is what stage 29 exercises, and the producers that reach it
are covered by their own tests.

### Frames replaced in place (M40 surgical refresh)

The Settings page grew three sections (Ambient, A2A, API guardrails) and
two Orchestrator knobs, so the archived frames whose visible region
includes the changed area were recaptured on the M40 build — same claim,
same settings state, same theme:

- `01-settings-models/02-formatter-section-default-on.png`
- `24-formatter/00-settings-on-a2ui-first.png`, `24-formatter/03-settings-off-options-hidden.png`
- `23-ops-fixes/02-otlp-endpoint-set.png`, `23-ops-fixes/03-debug-selected-visible.png`
  (the two paused `workspace-reporter` gates recreated live for fidelity)
- `17-data-purge/00-purged-settings.png`
- `25-memory/00-settings-memory-layers.png`
- `26-ambient/00-settings-no-ambient-toggle.png` → **renamed**
  `26-ambient/00-settings-ambient-section.png`: its claim inverted — the
  ambient master switch (with every §17 knob) now lives on the Settings
  page (spec §8.7, M40) instead of being API-only.

Frames whose visible region is unaffected (e.g. `01-settings-models/00`,
`01`, the stage-18 cache/retrieval frames) were left untouched; milestone
archive directories are never retouched.

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
3. **Per-control settings 422s failed silently** (stage 28, §14e-42). Every
   numeric/list/channel control on the Settings page runs its own
   `usePatchSettings` mutation, so a rejected out-of-bounds write never
   reached the page-level ErrorNote — the value just didn't stick. Each
   control now renders its own inline ErrorNote.
   Commit `fix(settings-ui): surface per-control PATCH errors inline`.
4. **The §4 skill overlap guard was silently dead in the editor** (stage 28,
   §14e-43). The editor's pre-save `check-overlap` payload included
   `max_tool_iterations`, which `SkillOverlapCheck` rejects
   (`extra_forbidden`); the advisory catch swallowed the 422 and every save
   fell straight through — the duplicate dialog could never fire from the
   skill editor. Payload now matches the schema.
   Commit `fix(skills-ui): overlap-guard check sent a field its schema forbids`.

## Honest notes

- **Stage 13's failed run is a genuine environmental failure, produced
  deliberately**: the model-side approaches all failed honestly (off-list
  model refs 422 at save — M33 validation working; qwen completes or
  declines gracefully; HITL deny completes with an honest report), so the
  failure was produced by severing provider egress at the sandbox proxy
  forwarder for one run — a real `APIConnectionError`, the same class of
  environmental failure as the prior campaign's natural rate-limit — then
  egress was restored and the retry driven live from the drawer.
- **The agentic plan-card frames (`08/09 …/01-plan-card-live.png`) are
  intentionally absent**: the transient "plan · agentic todos" card never
  surfaced across eight live attempts (both efforts, simple and multi-step
  prompts) — current qwen agentic runs answer without emitting todos, so the
  frame is not applicable in current behavior and was not carried over.
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
