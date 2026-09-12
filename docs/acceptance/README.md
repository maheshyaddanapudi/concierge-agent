# Acceptance evidence — campaign v1 (dev images)

One campaign, one tree. Every frame here was captured click-driven on the
`dev` images by the drivers in `experiments/acceptance/` against the live
model `openrouter:qwen/qwen3.8-max` (all roles unless a stage's claim *is* a
role mix), and every stage carries its own `transcript.md` — the driver's
log of what it did, what the API returned, and where it had to record a miss
instead of a frame. `INVENTORY.md` lists every asset the tree held before
this campaign and what became of it. `report.md` holds the findings.

## Stages (spec §14 script, then the later milestones)

| Stage | Claim |
|---|---|
| `00-fresh-slate` | the seed on an empty volume: servers, tools, skills, research-concierge, native tools, empty runs |
| `01-settings-models` | the configured provider, the default model chosen in the UI, the settings read back |
| `02-mcp-servers` | a stdio server registered in the UI, connected, its tools ingested; the drawer, refresh, reconnect |
| `03-tools` | the projected tools, a direct exposure switched on, badges, search |
| `04-skills` | the native skills, the editor with tool tags, a bad `{tool:…}` mention refused, `summarize-site` created and edited, `notes-formatter` exposed |
| `05-sub-agents` | the builder from a template, an error edge, a dangling edge refused, the overlap dialog, `site-analyst` saved, the DAG preview, a bound skill refusing deletion |
| `06`–`09` trials | graph/agentic × effort high/default: plan card, live rails, the HITL gate, the answer, a follow-up answered from the first turn, the trace |
| `10-fallback-uncovered-ask` | no confident match → the full-catalog fallback banner and rung |
| `11-hitl-deny-and-queue` | a gate approved from the Settings queue in a second tab; a gate denied with a note |
| `12-stop-and-queued-message` | a message queued while a run is live; ■ Stop; the queued draft fires next |
| `13-failure-retry-cancel` | an honest cannot-do answer; cancel from the Runs drawer; fallbacks off → a real failure; retry re-plans to completion; the failed row deleted |
| `14-runs-and-ops` | the Runs table, trace drawer, search, observability controls, the exposure-cap banner, an idempotent seed reload |
| `15-static-guards` | static records: definition fields locked, toggles live, no Delete |
| `16-theme-gallery` | the same settled answer in the four palettes; the picker restored |
| `17-data-purge` | the Runs table before → purge → empty → a clean run on the purged store |
| `18-registry-cache-and-retrieval` | bypass / memory / redis cache modes with runs, generation bumps on writes and toggles, refresh-all, top-K retrieval truncating the planner's catalog (backend log) |
| `19-multi-turn-conversations` | three-turn graph and two-turn agentic conversations answered from earlier turns |
| `20-heterogeneous-models` | planner and formatter on a different model/effort than the default, proven per step in the trace |
| `21-m8-features` | a form gate (text + choice) filled from the chat card; a chart inside the structured answer; agentic research with real fetched sources |
| `22-hitl-stale-card-fix` | a gate resolved from the queue collapses the chat card; a gate approved in chat drops from the queue |
| `23-ops-fixes` | OTLP endpoint and log level live; a per-run delete removes its checkpoints (counted in the DB); purge → empty |
| `24-formatter` | A2UI first, raw first, formatter off (no artifact, no toggle), presentation frozen per run |
| `25-memory` | the §16 lifecycle: layers, + Remember, extraction (preference active, instruction in review), provenance, approve, supersede, pin, recall citing the memory id, hard delete |
| `26-ambient` | a routine from the typed builder with a webhook trigger, a fire token issued in the UI, a real bearer-token fire (held / fired / 401), the run, the ledger and chain, both watch paths, the Inbox with feedback |
| `27-a2a` | the dark gate, a counterparty registered by card, write-only credentials, kind=a2a tools, a skill and ExComm on them, organic routing with fenced traces, the remote question as a HITL card (reply / deny), Stop cancelling the remote task, park → Inbox, a reply from the task drawer, card drift, the auth matrix |
| `28-config-hardening` | the per-conversation composer pin, the Settings sections with live nav toggling, read-back and an inline 422, the tick-bounded poll throttle, the overlap threshold, the live rate-limit settings, the ambient toast |
| `29-ambient-pursuit` | the presence × pursuit matrix against a live SMTP sink and an SMS-gateway-shaped webhook sink, quiet hours beating pursuit |
| `30-salience` | unseen deliveries judged live in auto mode: escalate leads the digest, drop dismisses; the unread badge; seen |
| `31-salience-decisions` | the propose surface: Do it / Leave it, "why this?", apply, Undo restoring the row exactly, decline; the two role-model pickers |
| `32-durable-forgetting` | Forget vs Erase, the content-free tombstone, re-admission suppressed and counted, Unforget, a learner proposal rejected |
| `33-evals` | a three-case dataset (exact / contains / llm_judge) uploaded and graded live, every case an ordinary run |
| `34-auth-builtin` | the login gate, admin signed in with the bootstrap password, a run under identity, a member's empty Runs page (driven by `prod/m34-auth.sh`) |
| `35-schema-drift` | tool schema drift (spec §3.2) and the pinned registry (§3.6): the stub server renames `echo`'s parameter under a live run — the Tools page badge, the drawer banner and its Acknowledge, the trace pinning the schema version before and after, the Settings policy toggle and the overlap judge's own model role, then the same change quarantined and re-enabled from the drawer |
| `36-hardening-wave` | the hardening wave (spec §3.2, §3.6, §8.3, §8.6, §8.7): an operator's tool description surviving a re-ingest of the stub server, a run whose trace names its entities and definition versions with the formatter as a step, the **Snapshot vs registry** panel reading all-same then `changed` after the skill is edited, the Skills list flagging a bound tool taken inactive, and Settings with the registry overlap audit gate, the eval judge's own model and the salience-judge hint; then (third reading) the overlap judge given a one-token output budget so its verdict cannot parse, and a skill saved through the UI — the save goes through with a "Saved unjudged" notice naming the error, never a silent 0% |

## Production-hardening drills

`prod/` holds the transcripts and frames of the shell drills in
`experiments/acceptance/prod/`, re-run on the same images: the builtin auth
matrix (M34), the load baseline (M49), routine quarantine and timezone
(M50), admission control, the wall clock and the 429 / 503 boundaries, the
redis-backed cache failing open (M51), untrusted content and secrets (M52),
readiness, metrics, retention, the spend ceiling, MCP reconnect, the
rolling deploy and the restore round trip (M53), recall at scale (M54), the
auth seam (M55), and the §14 ceremony with the performance record (M56).
`prod/FIXES/` re-verifies the campaign's findings 1 and 2 on the fixed
image (the HITL deny reported as a refusal; the ambient tick leading again
after `ambient_enabled` off→on) with the test suite on the fix commit;
stage 11 was re-run on that image and its directory replaced.

## How to re-run

```bash
cd experiments/acceptance && npm install
export ACC_BASE=http://localhost:5173 ACC_SHOTS=./shots ACC_MODEL=openrouter:qwen/qwen3.8-max
docker compose down -v && docker compose up -d           # a fresh slate for stage 00
node run.mjs stages/00-fresh-slate.mjs … stages/33-evals.mjs
node publish.mjs                                          # replaces docs/acceptance/<stage>/ wholesale
```

Stages 27–29 need the host-side counterparties and sinks described in
`experiments/acceptance/README.md`; the drills need `docker compose` and the
db container reachable through `docker exec`.
