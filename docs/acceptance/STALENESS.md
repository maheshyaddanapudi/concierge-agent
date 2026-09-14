# Staleness record — this evidence predates the current code

**Read this before you trust anything else in this tree.**

Every page under `docs/acceptance/` was captured on a build that is no longer
HEAD. The approved plan was to re-run and republish the whole tree live on a
real model after the hardening wave landed; **that re-run never happened** —
the provider account ran out of credit mid-session and the container's Docker
state was then lost, so no stack could be built or run. The wave's own commit
says so:

```
$ git show -s --format=%B 401914a | tail -8
NOT verified: the live acceptance re-run (spec §14 and the stage tree)
did not happen. The provider account ran out of credit mid-session and
the container's Docker state was then lost, so no stack could be built
or run. The published evidence under docs/acceptance/ therefore still
reflects the PREVIOUS build and predates this wave's prompt and recall
changes. Re-running and republishing it remains open.
```

That honesty lived only in a commit message. Nothing on any published page
said it. This file, and the banner now at the top of every transcript in the
tree, is what fixes that.

**Nothing in this tree has been re-verified.** No stage, drill or ceremony was
re-run in the pass that produced this page. Docker is dead in this environment
and there is no provider credit, so the only things executed were `git`, the
filesystem, and a backend test collection. Every claim below is a reading of
the committed code against the published claim — never an observation of a
running system.

---

## 1. What each page was captured against

No stage transcript records a commit SHA — the drivers never wrote one. What
each transcript *does* carry is an ISO capture timestamp in its first line, so
every attribution below is **timestamp + git timeline**, corroborated where a
transcript shows behaviour that only one commit could produce.

The commits that touched `backend/` or `frontend/` since the campaign began,
newest first:

| build | committed (UTC) | what it was |
|---|---|---|
| `3891914` | 2026-09-14 01:15 | **HEAD** — documentation only, no source |
| `401914a` | 2026-09-13 17:59 | **the hardening wave** — ~470 reviewer findings, 220 files |
| `9f9ee53` | 2026-09-12 15:07 | the unjudged-save fix |
| `ab07205` | 2026-09-11 23:09 | the third reading |
| `a4424a9` | 2026-09-11 21:46 | the hardening wave, round two |
| `58f77e7` | 2026-09-11 01:42 | schema drift and the pinned registry |
| `24e53b6` | 2026-09-10 23:53 | the campaign fixes (findings 1, 2, 4) |
| `b624908` | 2026-09-10 01:13 | release 1.0.0, M1–M56 — the campaign build |

Captures sit *between* commits because each pass built an image from a working
tree and ran the stages **before** committing it. So "captured on `ab07205`"
means: the tree that was committed as `ab07205` minutes later. The clearest
proof is stage 36 — its transcript runs `15:06:12Z → 15:07:07Z` and `9f9ee53`
was committed at `15:07:34Z`, 27 seconds after the log ends, and the transcript
shows the `judge_available` / "Saved unjudged" behaviour that
`git log -S"Saved unjudged"` attributes to `9f9ee53` alone.

Two independent sources agree on the third-reading set: the nine stages whose
timestamps fall in `2026-09-11 22:35–22:57` are exactly the nine `report.md`
says that pass re-ran, and `prod/HARDENING/tests.md` is headed
`2026-09-11T22:31Z — the third-reading commit`, four minutes before the first
of them.

| build captured on | source commits behind HEAD | stages |
|---|---|---|
| `b624908` | 6 | 00, 01, 06, 07, 08, 09, 10, 12, 13, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 29, 30, 31, 32, 33, 34 (26 stages) |
| `24e53b6` | 5 | 11 |
| `ab07205` | 2 | 02, 03, 04, 05, 14, 18, 27, 28, 35 |
| `9f9ee53` | 1 | 36 |

**Not one stage was captured on HEAD, and not one was captured on the wave.**

The drills under `prod/` are the same story. Three of them record a commit in
their own text — but those are *documentation* commits, and the code they ran
is older: `prod/M49/baseline.md` says commit `d47015c`, `prod/tests.md` says
`17acdc1`, `prod/frontend-tests.md` says `6f32ec6`. All three of those commits
sit between `b624908` and `24e53b6` with no source commit in between, so all
three ran `b624908`'s code. (That also confirms, from a primary source, what
`report.md` already claimed: the two test pages naming different commits are
code-identical.)

`prod/M54/load-n3-vs-n1.md` is older still — captured 2026-09-03 at commits
`354974d` and `d186208`, which is before the campaign build existed.

---

## 2. How affected is each page — graded, not blanket-labelled

Every page here is stale. That is not the same as every page being worthless: a
stage that photographs CRUD on a page the wave never opened is still a fair
picture of the system, while a stage whose whole subject the wave rewrote is
now misleading. Two grades:

- **C — the wave moved what this page claims.** A re-run would visibly differ,
  or the claim may no longer hold as photographed. **27 stages.**
- **B — the surface moved underneath, but the claim still stands.** Named
  deltas, none of them touching the thing the frames are evidence *for*.
  **10 stages.**

There is no grade A, and that is deliberate: no page in this tree was captured
on HEAD, so none can be called current.

| stage | captured on | behind HEAD | grade | why |
|---|---|---|---|---|
| `00-fresh-slate` | `b624908` | 6 | **C** | Captured before the seed pinned its filesystem MCP package. HEAD launches `@modelcontextprotocol/server-filesystem@2026.8.31`; this capture launched the spec unpinned, so the recorded `filesystem:active/14` and `25 tools` may not reproduce. The registry cache a fresh stack boots with also changed (`bypass` → `memory`). |
| `01-settings-models` | `b624908` | 6 | **C** | Settings grew from 116 to 122 keys and one default value changed (`registry_cache_mode` `bypass` → `memory`). The retention block on this page now lists nine tables, not six. |
| `02-mcp-servers` | `ab07205` | 2 | **B** | `McpServersPage.tsx` was not touched and the stdio registration this stage drives still succeeds — its `python` launcher is on the wave's new allowlist. What moved around it: operator-disable intent (`disabled_at`) and the launcher guard extended to PATCH. |
| `03-tools` | `ab07205` | 2 | **B** | Neither `ToolsPage.tsx` nor `api/tools.py` was touched by the wave. The registry cache behind the page now defaults to `memory` rather than `bypass`. |
| `04-skills` | `ab07205` | 2 | **B** | `api/skills.py` moved four lines and this stage captures no static-skill drawer, so the wave's static-record change does not reach these frames. The overlap judge on the save path moved five lines. |
| `05-sub-agents` | `ab07205` | 2 | **C** | `03-static-seed-card-drawer.png` shows the static sub-agent drawer — exactly where the wave added the Status toggle that the page claimed in its own copy and never rendered. The drawer in this frame is missing a control HEAD draws. |
| `06-trial-graph-thinking-on` | `b624908` | 6 | **C** | The trials photograph plan card, live rails, gate, answer and trace — the surfaces the wave rewrote: `ChatPage.tsx`'s event fold and gate consumption, `graph_mode` / `agentic_mode` / `planner` / `recorder` / `ladder`, and the `planner`, `router` and `concierge` prompts. |
| `07-trial-graph-thinking-off` | `b624908` | 6 | **C** | Same surfaces as stage 06: the chat event fold, the graph orchestrator and the planner/router/concierge prompts all moved under this capture. |
| `08-trial-agentic-thinking-on` | `b624908` | 6 | **C** | Same surfaces as stage 06, on the agentic path: `agentic_mode.py`, `ladder.py` and `ChatPage.tsx` all moved under this capture. |
| `09-trial-agentic-thinking-off` | `b624908` | 6 | **C** | Same surfaces as stage 08: the agentic loop, the escalation ladder and the chat event fold all moved under this capture. |
| `10-fallback-uncovered-ask` | `b624908` | 6 | **C** | This stage's whole subject is the full-catalog fallback rung. `prompts/fallback.md` is one of three prompt files the wave ADDED (+30 lines) and `ladder.py` was rewritten (+85/−9). |
| `11-hitl-deny-and-queue` | `24e53b6` | 5 | **C** | Captured on the campaign-fixes build. Since then `ChatPage.tsx`'s gate-consumption fold was rewritten precisely so a gate closed on another surface never leaves armed buttons behind, and `factory/worker.py` moved (+60/−5). |
| `12-stop-and-queued-message` | `b624908` | 6 | **C** | The queued-composer path these frames show sits inside `ChatPage.tsx`'s rewrite (refusals are now surfaced beside the composer with the draft kept), and a queued run is now cancellable from the Runs table. |
| `13-failure-retry-cancel` | `b624908` | 6 | **C** | `ladder.py` (+85/−9) drives the fallbacks-off failure this stage stages, `runner.py` moved (+86/−13), and the Runs table now offers cancel on queued rows. |
| `14-runs-and-ops` | `ab07205` | 2 | **C** | `RunsPage.tsx`, `api/runs.py`, `obs.py` (+95) and `seed/loader.py` (+68/−5) all moved — the runs list, the observability controls and the seed reload are three of this stage's six frames. |
| `15-static-guards` | `b624908` | 6 | **C** | **The sharpest mismatch in the tree.** This transcript records `static skill file-ops: … live switches: 1`. The wave added the Status toggle that `SkillsPage` and `SubAgentsPage` claimed and never rendered, so HEAD shows TWO live switches where `00-static-skill-drawer.png` shows one. This page documents the defect as though it were the proof of the rule. |
| `16-theme-gallery` | `b624908` | 6 | **B** | `theme.ts` changed only to guard `localStorage` against a browser that throws on it. No palette value moved, and the four palettes are CSS the wave did not touch. The answer text inside the frames would differ on a re-run because the prompts changed, but this stage's claim is about the palettes and it still holds. |
| `17-data-purge` | `b624908` | 6 | **C** | `00-purged-settings.png` shows the retention block, which the wave took from six tables to nine and gave six new settings keys; `retention.py` moved +195/−13. |
| `18-registry-cache-and-retrieval` | `ab07205` | 2 | **C** | **The most affected stage in the tree.** Its subject is the registry cache mode, and the wave flipped the shipped default from `bypass` to `memory` — the ONE default value that changed. This transcript also reads `settings:g33/116`; HEAD ships 122 settings keys. Its own honest note (the threshold field would not commit through the UI) names the control the wave rewrote. |
| `19-multi-turn-conversations` | `b624908` | 6 | **C** | `prompts/prior_outputs.md` — the mechanism by which a later turn is answered from an earlier one — is one of three prompt files the wave ADDED. `memory/inject.py` also moved (+31/−9). |
| `20-heterogeneous-models` | `b624908` | 6 | **B** | The role-model mechanism is intact: `app/llm/` moved 14 lines and no provider port, registry or adapter contract changed. `recorder.py`, which renders the per-step model in the trace this stage reads, did move. |
| `21-m8-features` | `b624908` | 6 | **C** | The chart pipeline was rebuilt: one shared `validate_chart_spec` contract for both chart paths, charts hoisted out of containers so a nested one can draw, numeric cells coerced instead of failing the whole artifact, unrenderable specs dropped with a log line. `summarize_and_structure.md` and its golden set also changed. |
| `22-hitl-stale-card-fix` | `b624908` | 6 | **C** | This stage's exact claim — a gate resolved on one surface collapsing on the other — is what `ChatPage.tsx`'s new event fold was written to guarantee ("never leave armed buttons on a dead gate"). The behaviour is probably still true; the implementation under the frames is not the one photographed. |
| `23-ops-fixes` | `b624908` | 6 | **C** | `retention.py` (+195/−13), six new retention keys and `obs.py` (+95) sit under all five frames, and the retention block these settings frames neighbour now lists nine tables rather than six. |
| `24-formatter` | `b624908` | 6 | **C** | `answer_ui.py` (+81/−18), `AnswerPanel.tsx` and `ChartSvg.tsx` (+217/−90) are the formatter this stage photographs in four modes. |
| `25-memory` | `b624908` | 6 | **C** | Both of this stage's named frames sit on changed behaviour: recall's relevance model was REPLACED (rank-normalized RRF → a blend of absolute cosine and lexical coverage, with the score floor now gating relevance itself), and supersede no longer drops a memory's project scope. `memory_sections.md` is one of the three prompt files the wave added. |
| `26-ambient` | `b624908` | 6 | **C** | A routine's allowlist is now a real ceiling in both orchestrator modes (`execute.py` +23/−10, new `allowlist_audit.py` +147), `triggers.py`, `watch_compile.py` and `channels.py` moved, and `ambient_intent_run.md` gained 14 lines. |
| `27-a2a` | `ab07205` | 2 | **C** | `32-card-drift-new-skill.png` and `33-drift-tool-projected.png` sit on the card-refresh path the wave changed twice: operator-disable intent (`disabled_at`) is now honoured by refresh, and a new unique index stops two overlapping refreshes from double-inserting an agent's tools. |
| `28-config-hardening` | `ab07205` | 2 | **C** | Eight of this stage's frames are Settings. The wave grew Settings from 116 to 122 keys, rewrote number-field commit so a rejected value says so instead of silently reverting (this stage's `11-settings-422-inline.png`), made `0` typeable where it is the documented off value, and added `limits.py` behind `13-settings-api-guardrails.png`. |
| `29-ambient-pursuit` | `b624908` | 6 | **B** | The pursuit × presence matrix itself did not move: `presence.py` and `deliver.py` each gained a five-line master-gate guard that is a no-op on this stage's path, which runs with ambient on. `channels.py` moved +22/−1. |
| `30-salience` | `b624908` | 6 | **B** | `delivery_salience.md`, the judge's own prompt, was NOT touched, and `salience.py` changed only to ledger the judge's spend and check the ceiling — a no-op below the ceiling. The verdicts recorded here remain representative. |
| `31-salience-decisions` | `b624908` | 6 | **B** | `decide.py` gained only the five-line master-gate guard, and the judge's prompt was not touched. The two role-model pickers this stage frames live on `SettingsPage.tsx`, which did move. |
| `32-durable-forgetting` | `b624908` | 6 | **C** | `store.py` (+93/−13) and `lifecycle.py` (+71/−13) changed the supersede and bi-temporal close paths this stage exercises, including a fix for an inverted valid-from/valid-to interval that left a row visible at no point in time. |
| `33-evals` | `b624908` | 6 | **C** | The eval harness no longer auto-approves the human gates it reaches — that is now per-dataset opt-in and every machine-cleared gate is recorded (`evals/runner.py` +107/−10, `api/evals.py` +87/−5, `EvalsPage.tsx`). |
| `34-auth-builtin` | `b624908` | 6 | **B** | `backend/app/auth/` — the provider port, the registry and the builtin provider this stage is about — was NOT touched by the wave. The request pipeline around it was (`api/deps.py` +25, `main.py` +77, and the new `limits.py`). |
| `35-schema-drift` | `ab07205` | 2 | **B** | The drift path itself barely moved: `toolschema.py` gained four lines (a new `ingest_state` for an operator-disabled server) and the badge, drawer banner, Acknowledge and quarantine surfaces are unchanged. Separately, this directory holds EIGHT frames its transcript does not name — see the orphan-frame section of `../STALENESS.md`. |
| `36-hardening-wave` | `9f9ee53` | 1 | **C** | The newest evidence in the tree, and still falsified in a recorded value: this transcript reads `prompts=24 files`, while HEAD ships 27 prompt `.md` files. The snapshot this stage photographs therefore pins a different set than the one it names. |

### The drills

| drill | captured on | grade | why |
|---|---|---|---|
| `prod/M34/` | `b624908` | **B** | `backend/app/auth/` was not touched by the wave; the request pipeline around it was (`api/deps.py`, `main.py`, the new `limits.py`). |
| `prod/M49/` | `b624908` | **C** | The load baseline was measured before `limits.py` existed: the inbound rate limiter used to sit behind auth, which ships dark, so this run never met it. On HEAD the limiter is unconditional and the harness has to raise its keys for the duration of a run. |
| `prod/M50/` | `b624908` | **B** | Trigger validation and timezone handling; `ambient/triggers.py` gained 15 lines under this capture. |
| `prod/M51/` | `b624908` | **C** | Admission, the wall clock and the 429/503 boundaries all sit under `limits.py` (a new module, +115), `cost.py` (+128, the new `job_usage` ledger) and `runner.py` (+86/−13). |
| `prod/M52/` | `b624908` | **B** | `egress.py` moved only slightly; the fence and secret-masking behaviour this drill proves was not the wave's subject. `main.py` (+77) now also bounds request bodies and stops a validation error echoing the request. |
| `prod/M53/` | `b624908` | **C** | The spend ceiling this drill exercises now counts background model calls through a new `job_usage` ledger, and retention grew from six tables to nine with six new settings keys. |
| `prod/M54/` | **mixed — see below** | **B / C** | This folder is the one place two different capture dates sit side by side, so it is bannered per file rather than per folder. |
| `prod/M55/` | `b624908` | **B** | The auth seam itself (`backend/app/auth/`) was not touched by the wave. |
| `prod/M56/` | `ab07205` | **C** | The §14 ceremony end to end: it crosses the prompts, the orchestrator, the formatter, the settings surface and the seed, all of which the wave moved. |
| `prod/FIXES/` | `24e53b6` | **B** | The two regressions re-verified here (a HITL deny reported as a refusal, the ambient tick leading again after off→on) were not re-opened by the wave, but `factory/worker.py` and the ambient loop both moved under them. |
| `prod/DRIFT/` | `58f77e7` | **B** | The drift rule itself barely moved in the wave (`toolschema.py` +4). Captured two builds before the wave nonetheless. |
| `prod/HARDENING/` | `ab07205` | **C** | `hardening-wave.md` was captured on the round-two build and `third-reading.md` on the third-reading build. Both predate the wave, which changed the pinned-snapshot contents these drills read back — HEAD ships 27 prompt files where these pages record 24. |

#### `prod/M54/` in detail — the oldest evidence in the tree

Six of its seven transcripts were captured on **2026-09-03**, a week before the
campaign build existed. Their own headers say so
(`# M54 fleet — cold boot of three replicas — 2026-09-03T00:30:30Z`), and
`report.md` already noted they were "kept from the same day's capture on the
merged code".

| file | captured | build | behind HEAD | grade |
|---|---|---|---|---|
| `cold-boot.md` | 2026-09-03 00:30 | `0c4011b` | 13 | **B** |
| `cross-replica-cancel.md` | 2026-09-03 00:42 | `0c4011b` | 13 | **B** |
| `delivery-fan-out.md` | 2026-09-03 00:43 | `0c4011b` | 13 | **B** |
| `job-clock.md` | 2026-09-03 00:47 | `0c4011b` | 13 | **B** |
| `rate-limiter.md` | 2026-09-03 00:50 | `0c4011b` | 13 | **B** |
| `load-n3-vs-n1.md` | 2026-09-03 00:52 / 00:54 | `354974d` → `d186208` | 12 | **C** |
| `recall.md` | 2026-09-10 | `b624908` | 6 | **C** |

`354974d` is a documentation commit over `0c4011b`'s code; `d186208` is a
test-only source commit. The five fleet legs at 00:30–00:50 precede
`0c4011b`'s own commit timestamp (00:49:16) by the usual margin — they ran the
working tree that became it.

---

## 3. What the wave actually changed, in numbers

Everything below was checked against the repository in this pass. The command
is given so it can be re-checked.

| fact | before the wave (`9f9ee53`) | HEAD | how it was checked |
|---|---|---|---|
| files changed by `401914a` | — | 220 | `git show --stat --name-only --format="" 401914a \| grep -cvE '^$'` |
| `backend/app` files changed | — | 85 | same, filtered to `^backend/app` |
| `frontend/src` files changed | — | 16 | same, filtered to `^frontend/src` |
| settings keys in `DEFAULTS` | 116 | **122** | parsed the `DEFAULTS` block at both revisions |
| settings default *values* changed | — | **exactly 1** | same parse, compared values |
| `registry_cache_mode` default | `bypass` | **`memory`** | `git show 401914a -- backend/app/settings_store.py` |
| prompt `.md` files | 24 | **27** | `git ls-tree -r --name-only <rev> backend/app/prompts/ \| grep -c '\.md$'` |
| prompt files edited by the wave | — | 12 (8 `.md` + 4 golden `.yaml`) | `git show --numstat --format="" 401914a -- backend/app/prompts/` |
| retention tables on the Settings page | 6 | **9** | the `SettingsPage.tsx` diff, "The six tables" → "The nine tables" |
| seed's filesystem MCP package | unpinned | **pinned `@2026.8.31`** | `backend/app/seed/loader.py:37`, `backend/Dockerfile:11` |

The three **new** prompt files are `fallback.md`, `memory_sections.md` and
`prior_outputs.md` — which is why stages 10, 25 and 19 are graded C: each of
those stages exists to demonstrate the very mechanism one of those files now
carries.

The one replaced algorithm worth naming on its own is memory recall. Relevance
was a rank-normalized reciprocal-rank fusion of the two legs; it is now a blend
of their **absolute** scores (cosine from the vector leg, query coverage from
the lexical one, weighted 0.4 / 0.6), and the score floor now gates absolute
relevance as well as the composite. The module's own new docstring explains
why: with rank-normalized relevance "no query could ever return empty over a
non-empty store". Every recall number and every recall frame in this tree was
taken under the old model.

### What the wave did NOT touch

This is why some stages keep a B. None of the following appear in `401914a`:

- `backend/app/auth/` — the provider port, registry and builtin provider (stage 34, `prod/M34`, `prod/M55`)
- `backend/app/api/tools.py`, `memories.py`, `ambient.py`, `routines.py`, `cache.py`, `ops.py`, `seed.py`, `auth.py`
- `frontend/src/pages/ToolsPage.tsx`, `McpServersPage.tsx`, `MemoryPage.tsx`, `AmbientPage.tsx`
- `frontend/src/components/` — `AmbientToaster`, `AnswerUiView`, `CacheControls`, `LoginGate`, `Markdown`, `OverlapDialog`, `RegistryTable`, `TableBlock`, `ui`
- `backend/app/prompts/delivery_salience.md` — the salience judge's own prompt (stages 30, 31)
- the four theme palettes (`theme.ts` changed only to guard `localStorage`)

---

## 4. Counts audited against the disk

Every number on `README.md`, `report.md` and `INVENTORY.md` was recounted in
this pass. Most were right. These are the ones that were not, with the proof.

**Corrected — the end-of-campaign totals.** Both `report.md` and `INVENTORY.md`
said the tree held **377 files** at the end of the campaign and that `prod/`
held **22 transcripts**. Counted at `bf04afc`, the commit that closed the
campaign:

```
$ git ls-tree -r --name-only bf04afc docs/acceptance/ | wc -l
379
$ git ls-tree -r --name-only bf04afc docs/acceptance/prod/ | grep -c '\.md$'
24          # minus prod/README.md, prod/tests.md, prod/frontend-tests.md = 21
```

So **377 → 379 files** and **22 → 21 drill transcripts**. The frame counts on
the same sentences were right (283 stage frames, 20 under `prod/`, 303 total,
35 stage directories, 9 drill folders — all confirmed at `bf04afc`).

**Corrected — the file model leaves six files unlisted.** Today's totals are
all correct (424 files, 336 frames, 316 across 37 stage directories, 20 under
`prod/`, 12 drill folders, 31 drill transcripts, 8 drill data files, 60 MB —
every one recounted and confirmed). But the *model* those pages describe adds
up to 418, not 424. The six files nothing names:

| file | why it is unlisted |
|---|---|
| `29-ambient-pursuit/03-pursuit-matrix-transcript.txt` | a stage-written data file; the pages count only frames and `transcript.md` per stage |
| `30-salience/05-salience-transcript.txt` | ditto |
| `31-salience-decisions/transcript-decisions.txt` | ditto |
| `32-durable-forgetting/transcript-leg1-hash-only.txt` | ditto |
| `33-evals/quiz-eval.csv` | ditto |
| `coordination_m35/report.md` | a 39th directory — see below |

**Corrected — `coordination_m35/` is still here.** `INVENTORY.md` gives its
disposition as "kept as `prod/M54`", which reads as though it moved. It did
not: `docs/acceptance/coordination_m35/report.md` is still on disk, holds 2262
bytes, is referenced by nothing but that one inventory row, and is outside both
the "37 stage directories" and the "12 drill folders" the pages count by.

**Confirmed as still true — the eight orphan frames in `35-schema-drift/`.**
The previous sweep's note is accurate and remains accurate:

```
$ ls docs/acceptance/35-schema-drift/*.png | wc -l
21
$ grep -oE '[0-9]{2}[a-z]?-[a-z0-9-]+\.png' 35-schema-drift/transcript.md | sort -u | wc -l
13
```

The eight the transcript does not name are exactly the eight `INVENTORY.md`
lists (`01-drawer-schema-v7/v9`, `02-trace-tool-call-schema-v7/v9`,
`04-drawer-banner-v8/v10`, `12-trace-tool-call-schema-v9/v11`). They are the
hardening-wave and second-reading readings of the same stage, superseded by the
third-reading frames. **They are kept, not deleted** — deleting published
evidence is not this pass's call.

**Confirmed — the per-directory `frames` column in `INVENTORY.md` is
historical, not current.** It reports the tree as it stood at `28732b4`, the
start of the campaign, which is what the page says it does. Spot-checked:
`05-sub-agents` is listed as 8 frames and holds 7 today; at `28732b4` it held 8.
`18-registry-cache-and-retrieval` is listed as 13 and holds 14 today; at
`28732b4` it held 13. The column is right and must not be "corrected".

---

## 5. The published evidence was never assertion-gated

`experiments/acceptance/README.md` has a section headed **"Stages assert, they
do not report"**, describing `expect`, `expectStatus`, `expectHttp`,
`expectVisible` and `expectStep`, and saying a stage that merely logged its
outcome "would 'pass' with its run failed or its gate never armed". A reader
would reasonably assume the tree below was produced under that regime.

It was not. Those helpers entered `lib.mjs` in `401914a` — after every capture
in this tree:

```
$ git log --oneline -S"export function expect(" -- experiments/acceptance/lib.mjs
401914a feat: the code/setting/UI hardening wave — ~470 reviewer findings closed

$ grep -rl "ok — " --include=transcript.md docs/acceptance/ | wc -l
0          # out of 37 stage transcripts
```

Not one published transcript contains a single assertion line, because the
drivers that produced them had no assertions to log. The `zz-failure.png`
publish gate is older and did exist, but it only fires on an uncaught throw,
and before the helpers landed almost nothing threw on a wrong outcome. **Every
stage in this tree was judged by a human reading frames, not by the drivers.**

---

## 6. What could not be verified in this pass

Stated plainly, because guessing is the failure this pass exists to prevent.

1. **Whether any stage would still pass.** Docker is dead and there is no
   provider credit. Nothing here was re-run. Every grade above is a reading of
   the diff against the claim, not an observation of the system.
2. **Whether the seeded tool counts still hold.** Stage 00 records
   `filesystem:active/14` and `25 tools` against an *unpinned*
   `@modelcontextprotocol/server-filesystem`; HEAD pins `@2026.8.31`. Whether
   that version yields the same 14 tools cannot be checked without a stack.
3. **Whether stage 18's threshold field now commits.** Its honest note records
   the field silently reverting; the wave rewrote exactly that control to say
   what happened instead. Whether the same root cause is the one fixed is
   untested.
4. **The "55 MB" end-of-campaign size** on `report.md` and `INVENTORY.md`.
   Today's 60 MB was measured; the historical figure needs a checkout of
   `bf04afc` and was not measured.
5. **`report.md`'s "The first pass flagged 31 of ~150 frames."** This describes
   a QA pass over a tree that no longer exists in that shape. No primary source
   in the repository records either number.
6. **The round-two suite numbers (1152 / 107)** that `report.md` and the
   CHANGELOG carry. Their pages were overwritten by the third-reading run, as
   both pages already say; there is nothing left to check them against.
7. **Frame content.** Frames are PNGs. This pass read filenames, transcripts
   and code — it did not open a single image. Where a grade says a frame shows
   something, that comes from the frame's name and the transcript line that
   took it.
8. **HEAD's own test suite.** A full backend run was attempted on `3891914`
   and did **not** complete — it was terminated at 74 %, and the repository's
   working tree was being edited by another process while it ran, so the
   failures it had reached are unattributable. What *did* complete is
   collection: `pytest --collect-only` summed to **1246 tests**, consistent
   with the 1245 passed / 1 skipped that `401914a`'s commit message claims.
   No suite number anywhere in this tree has been re-measured, and none should
   be quoted from this pass.

---

## 7. For whoever runs the re-run

- Clear `ACC_SHOTS/<stage>/` is no longer needed — the capture directory is now
  cleared by `lib.mjs:stageStart()` as of `401914a`. That fix has **never been
  exercised**, because no stage has been run since it landed. The eight orphan
  frames in `35-schema-drift/` are residue of the old behaviour and will not
  reappear.
- `publish.mjs` replaces a stage directory wholesale, so the banner at the top
  of each transcript disappears by itself the moment that stage is genuinely
  re-run and republished. The warning cannot outlive the staleness.
- Start from `docs/acceptance/README.md`'s "How to re-run", and re-check every
  count in §4 above afterwards; the totals there describe today's stale tree,
  not the one a re-run will produce.
