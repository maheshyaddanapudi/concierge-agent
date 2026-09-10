# Campaign v1 report — regression, enhancements and the production drills on the dev images

**When**: 2026-09-10 · **Images**: the `dev` head after PR #25 (release 1.0.0, M1–M56) · **Model**: `openrouter:qwen/qwen3.8-max` as `default_model` for all roles, except stage 20 whose claim is a role mix · **Drivers**: `experiments/acceptance/` (Playwright stages, shell drills), checked in and environment-parametrised · **Stack**: `docker compose up` from a fresh volume for stage 00, carried forward in order.

## What was run

- **Parity** (stages 00–24): the original §14 script and the later milestone stages, re-driven click by click on the dev images. Every stage passed; the frames replace the earlier campaign's directories one for one (stage 19 is now `19-multi-turn-conversations`, see below).
- **Enhancements** (stages 25–34): memory, ambient, A2A, configuration hardening, pursuit, salience, salience decisions, durable forgetting, evals and the builtin auth provider — each rebuilt as a driver from the earlier campaign's transcripts, run live, and published with its transcript.
- **Production drills** (`prod/`): the M49–M56 drills ported to `experiments/acceptance/prod/` and re-run.

Every frame was judged against the claim in its name by an adversarial screenshot QA pass (live frames must show live indicators, settled frames must not, traces must have the claimed step in frame, second-tab frames must show the claimed surface). The first pass flagged 31 of ~150 frames; every flag traced to four driver defects (a hash navigation kept the settings query cache stale, the trace drawer opened the follow-up run instead of the trial run, the retry frame was taken behind the drawer, the tools cache header scrolled out of frame) and the affected stages were re-shot after the fixes.

## Findings

1. **After a HITL deny the aggregator claims success.** Stage 11: the reviewer denied the gate with the note "Do not publish…"; the DAG took the deny path (the trace shows `hitl` with `status: denied` and the note, and the `finish` skill never ran), yet the aggregate step's answer read "[Published successfully] The summary was published…". The trace is right; the answer contradicts it. Candidate defect: the aggregator does not carry the denial into the final answer.
2. **Flipping `ambient_enabled` off and on stalls the leader tick until a restart.** Reproduced three times out of four on the dev image: `PATCH /settings {"ambient_enabled": false}`, one second later `{"ambient_enabled": true}` (the Settings switch does exactly this). The loop surrenders the lease when it sees ambient dark (`_tick` → `lease.release()`), and never leads again: `pg_locks` holds no advisory lease, `concierge_ambient_leader` reads 0, no `ambient_leader_acquired` / `ambient_leader_error` / `ambient_tick_failed` line follows, tier-0 rows inserted afterwards stay undelivered indefinitely, and `py-spy` shows every thread idle (the stuck await is inside the asyncio task, which `py-spy dump` cannot show). `docker compose restart backend` re-acquires the lease within one tick and flushes the backlog. A tick-interval edit alone (45 → 5 (422) → 60 → 15) does not trigger it. Stage 28 therefore runs its master-switch leg last, and stage 29 runs a preflight probe so a stalled tick is named rather than misread as a held delivery. Candidate defect in `app/ambient/drain.py` / `coordinate.py`: the release-then-reacquire path after a dark→lit transition.
3. **The rate limiter runs only for identified principals.** The token bucket lives in the auth middleware; with auth dark every request passes through untouched (byte-identity by design). The 429 boundary is therefore proven under `AUTH_ENABLED=1` in the M34 drill, not in stage 28.
4. **The formatter's chart is nondeterministic for the same ask.** One run produced a chart component (rendered as the app's SVG bar chart), the next an ASCII chart in markdown with no artifact. Stage 21 retries the ask up to three times and logs each attempt; the published frame is a real chart component.
5. **The scripted A2A counterparty's "ask" script asks on every task**, so a skill loop that calls the remote tool more than once raises a gate per call. The driver answers each gate and drops the script after the first answer (a real agent asks once). Not a product finding, but it shaped the evidence.
6. **Private-address counterparties are refused by the egress policy** unless named in `EGRESS_ALLOW_HOSTS` — the M52 guard working as specified; the stage documents the setting it needs.
7. **No embeddings provider is configured** (OpenRouter is chat-only), so durable forgetting shows only the exact-text suppression leg; the semantic legs from the earlier campaign are stated as not exercisable here rather than re-shot.

## Honest notes

- **Stage 19 proves conversational continuity, not a provider swap** — only one provider is configured, the same substitution the previous campaign made.
- **The trials have no distinct "mid-run before the gate" frame**: the stub tools answer in milliseconds, so by the time the sub agent's rail renders, its gate is armed. The frame is named `02-rails-live-run`.
- **Stage 02's refresh-tools frame shows the click, not a busy state**; the refresh completes faster than a frame can catch. Renamed to what it shows.
- **The overlap judge is a model call** and flags near-duplicates most, not all, of the time; each stage records what it did.
- **Stage 26's Inbox frame** shows deliveries that include the diagnostic probes seeded while investigating finding 2, alongside the routine's own digest item.
- **Stage 31's second decision round** is not a separate proposal in this build: after Undo the row offers no second "Do it"; one round (apply → undo → decline) is the evidence.
- **The sandbox recycled itself twice mid-campaign** (docker and every background process died at 03:44 and 18:48 UTC); the stack was rebuilt on the same volume each time and every captured stage had already been committed.

## Stack state at the end

`default_model = openrouter:qwen/qwen3.8-max`, `orchestrator_mode = graph`, formatter on / A2UI first, memory on (all layers), ambient on, A2A on, registry cache as the drills left it; the sinks and counterparties are host processes outside the compose stack.
