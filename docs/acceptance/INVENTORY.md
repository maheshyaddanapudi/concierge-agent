# Acceptance evidence inventory (campaign acceptance_v1)

> ## ⚠ THIS INVENTORY DESCRIBES A STALE TREE
>
> Every directory listed here holds evidence captured on a build that is no
> longer HEAD (`3891914`). The hardening wave (`401914a`) landed after the last
> capture and **the planned live re-run never happened**. See
> [`STALENESS.md`](STALENESS.md) for what each page was captured against and
> how far its claim has moved.
>
> **Two things on this page were re-audited and corrected**: the
> end-of-campaign totals (below, marked **[corrected]**), and the fact that the
> file model here accounts for **418 of the 424 files on disk**. The six it
> does not name are the five stage-written data files in stages 29–33
> (`.txt` / `.csv`, which are neither frames nor `transcript.md`) and
> `coordination_m35/report.md`. That last one is a **39th directory that is
> still physically present**: its disposition below reads "kept as `prod/M54`",
> which suggests it moved, but `docs/acceptance/coordination_m35/report.md` is
> still on disk, is referenced by nothing except that row, and falls outside
> both the "37 stage directories" and the "12 drill folders" this page counts by.
>
> Everything else on this page was recounted against the disk and is correct —
> including the per-directory `frames` column, which is a **historical** record
> of the tree at `28732b4` and must not be "corrected" to today's counts.

Every asset in `docs/acceptance/` as it stood at the start of the campaign (commit `28732b4`, the merge of PR #25 into `dev`), what it claims to prove, when it was captured, and its **disposition** — `recaptured` (the same moment re-driven on the dev images and filed under the consolidated tree), `dropped` (nothing in the current spec asks for it, or a duplicate), `kept` (transcript-only evidence that is still the record). Dispositions are filled in as the passes complete; `pending` means not yet decided.

| directory | assets | frames | captured | proves | disposition |
|---|---|---|---|---|---|
| `00-fresh-slate` | 6 | 6 | 5ec9e77 2026-08-28 | stage 00-fresh-slate | recaptured (v1, dev images) |
| `01-settings-models` | 3 | 3 | c489327 2026-08-28 | stage 01-settings-models | recaptured (v1, dev images) |
| `02-mcp-servers` | 7 | 7 | 5ec9e77 2026-08-28 | stage 02-mcp-servers | recaptured (v1, dev images) |
| `03-tools` | 7 | 7 | 5ec9e77 2026-08-28 | stage 03-tools | recaptured (v1, dev images) |
| `04-skills` | 7 | 7 | 5ec9e77 2026-08-28 | stage 04-skills | recaptured (v1, dev images) |
| `05-sub-agents` | 8 | 8 | 5ec9e77 2026-08-28 | stage 05-sub-agents | recaptured (v1, dev images) |
| `06-trial-graph-thinking-on` | 10 | 10 | 5ec9e77 2026-08-28 | stage 06-trial-graph-thinking-on | recaptured (v1, dev images) |
| `07-trial-graph-thinking-off` | 9 | 9 | 5ec9e77 2026-08-28 | stage 07-trial-graph-thinking-off | recaptured (v1, dev images) |
| `08-trial-agentic-thinking-on` | 9 | 9 | 5ec9e77 2026-08-28 | stage 08-trial-agentic-thinking-on | recaptured (v1, dev images) |
| `09-trial-agentic-thinking-off` | 8 | 8 | 5ec9e77 2026-08-28 | stage 09-trial-agentic-thinking-off | recaptured (v1, dev images) |
| `10-fallback-uncovered-ask` | 3 | 3 | 5ec9e77 2026-08-28 | stage 10-fallback-uncovered-ask | recaptured (v1, dev images) |
| `11-hitl-deny-and-queue` | 6 | 6 | 5ec9e77 2026-08-28 | stage 11-hitl-deny-and-queue | recaptured (v1, dev images) |
| `12-stop-and-queued-message` | 3 | 3 | 5ec9e77 2026-08-28 | stage 12-stop-and-queued-message | recaptured (v1, dev images) |
| `13-failure-retry-cancel` | 8 | 8 | 5ec9e77 2026-08-28 | stage 13-failure-retry-cancel | recaptured (v1, dev images) |
| `14-runs-and-ops` | 7 | 7 | 5ec9e77 2026-08-28 | stage 14-runs-and-ops | recaptured (v1, dev images) |
| `15-static-guards` | 3 | 3 | 5ec9e77 2026-08-28 | stage 15-static-guards | recaptured (v1, dev images) |
| `16-theme-gallery` | 9 | 9 | 5ec9e77 2026-08-28 | stage 16-theme-gallery | recaptured (v1, dev images) |
| `17-data-purge` | 5 | 5 | c489327 2026-08-28 | stage 17-data-purge | recaptured (v1, dev images) |
| `18-registry-cache-and-retrieval` | 13 | 13 | 5ec9e77 2026-08-28 | stage 18-registry-cache-and-retrieval | recaptured (v1, dev images) |
| `19-provider-agnostic` | 5 | 5 | 5ec9e77 2026-08-28 | stage 19-provider-agnostic | recaptured as `19-multi-turn-conversations` (one provider configured; continuity proven instead of a provider swap) |
| `20-heterogeneous-models` | 4 | 4 | 5ec9e77 2026-08-28 | stage 20-heterogeneous-models | recaptured (v1, dev images) |
| `21-m8-features` | 5 | 5 | 5ec9e77 2026-08-28 | stage 21-m8-features | recaptured (v1, dev images) |
| `22-hitl-stale-card-fix` | 6 | 6 | 5ec9e77 2026-08-28 | stage 22-hitl-stale-card-fix | recaptured (v1, dev images) |
| `23-ops-fixes` | 5 | 5 | c489327 2026-08-28 | stage 23-ops-fixes | recaptured (v1, dev images) |
| `24-formatter` | 6 | 6 | c489327 2026-08-28 | stage 24-formatter | recaptured (v1, dev images) |
| `25-memory` | 12 | 12 | c489327 2026-08-28 | stage 25-memory | recaptured (v1, dev images) |
| `26-ambient` | 13 | 13 | c489327 2026-08-28 | stage 26-ambient | recaptured (v1, dev images) |
| `27-a2a` | 40 | 40 | 5ec9e77 2026-08-28 | stage 27-a2a | recaptured (v1, dev images, four scripted counterparties) |
| `28-config-hardening` | 25 | 24 | 783643e 2026-08-28 | stage 28-config-hardening | recaptured (v1, dev images; the 429 transcript lives in prod/M34) |
| `29-ambient-pursuit` | 4 | 3 | 9720be8 2026-08-28 | stage 29-ambient-pursuit | recaptured (v1, dev images, live SMTP + webhook sinks) |
| `30-salience` | 14 | 11 | 4fb2b8a 2026-08-29 | stage 30-salience | recaptured (v1, dev images; the regression sample is superseded by the QA pass) |
| `31-salience-decisions` | 15 | 12 | 5bab618 2026-08-30 | stage 31-salience-decisions | recaptured (v1, dev images; one decision round — Undo leaves no second proposal) |
| `32-durable-forgetting` | 14 | 10 | 915ced7 2026-08-30 | stage 32-durable-forgetting | recaptured (v1, dev images; exact-text leg only — no embeddings provider here) |
| `(root)` | 4 | 0 | e71305a 2026-09-10 | campaign (root) | replaced — one README (index), one report, this inventory |
| `a2a-14d` | 46 | 39 | 5ec9e77 2026-08-28 | spec §14d steps 33–40 on five scripted counterparties | recaptured as stage `27-a2a` on four scripted counterparties (removed from the tree; git history keeps it) |
| `ambient_channels_m29` | 3 | 2 | ae68c1e 2026-08-25 | campaign ambient_channels_m29 | recaptured as stages `26-ambient` / `29-ambient-pursuit` (removed; git history keeps it) |
| `ambient_m23` | 7 | 6 | 5ab6f69 2026-08-25 | campaign ambient_m23 | recaptured as stage `26-ambient` (removed; git history keeps it) |
| `ambient_m25` | 2 | 1 | 7e261f7 2026-08-25 | campaign ambient_m25 | recaptured as stage `26-ambient` (removed; git history keeps it) |
| `ambient_ui_m30` | 11 | 10 | aa13608 2026-08-25 | campaign ambient_ui_m30 | recaptured as stages `26-ambient` / `28-config-hardening` (removed; git history keeps it) |
| `archive` | 334 | 326 | 5ec9e77 2026-08-28 | earlier campaigns superseded by the ones above (walkone retest, first campaign frames) | dropped — superseded twice over; git history keeps every frame |
| `auth_m34` | 6 | 4 | 0da8f60 2026-08-26 | campaign auth_m34 | recaptured as `prod/M34/auth-drill.md` + stage `34-auth-builtin` (removed; git history keeps it) |
| `ceremony_m36` | 68 | 66 | a404e64 2026-08-26 | the M36 full acceptance ceremony (spec §18.10) | recaptured as `prod/M56` (the ceremony re-run on the dev images; removed; git history keeps it) |
| `coordination_m35` | 1 | 0 | d0ab4c0 2026-08-26 | campaign coordination_m35 | kept as `prod/M54` (the fleet drills captured on the merged code the same day) |
| `evals_m32` | 4 | 3 | 4537a6e 2026-08-25 | campaign evals_m32 | recaptured as stage `33-evals` (removed from the tree; git history keeps it) |
| `prod` | 94 | 31 | ae19740 2026-09-10 | the production-hardening drills M49–M56 | re-run on the dev images: M34 (new), M49, M50, M51, M52, M53, M54 recall, M55, M56 ceremony + addendum + perf record; the M54 fleet legs kept from the same day's capture on the merged code; the per-milestone tests.md pages replaced by one `prod/tests.md` |

Totals at the start: 879 assets, 775 frames, 133 MB. At the end of the campaign: **379** files, 303 frames (283 in the 35 stage directories, 20 under `prod/`), 55 MB — one tree, every directory captured in this campaign except the six M54 fleet transcripts kept from the same day's capture on the merged code. **[corrected]** — this read "377 files"; `git ls-tree -r --name-only bf04afc docs/acceptance/ | wc -l` is 379. The frame counts on this sentence were re-checked at `bf04afc` and are right; the 55 MB was not re-measured.

**The tree today**, after the post-campaign fix, schema-drift, hardening-wave and third-reading passes: **425 files, 336 frames (316 across 37 stage directories, 20 under `prod/`), 60 MB** — 37 stage transcripts, 12 drill folders under `prod/` holding 31 transcripts and 8 captured data files (`.json` / `.txt`), plus `prod/README.md`, `prod/tests.md`, `prod/frontend-tests.md` and this tree's four root pages (`README.md`, `report.md`, this inventory and `STALENESS.md`). Every one of those numbers was recounted against the disk in the staleness pass; the file total was 424 before that pass added `STALENESS.md`. Six of the 425 are named by no count on this page — see the note at the top.

After the campaign, the fixes for findings 1, 2 and 4 added `prod/FIXES/` (three transcripts, no frames) and replaced `11-hitl-deny-and-queue` with its re-run on the fixed image (six frames, one transcript — same names). The schema-drift work added stage `35-schema-drift` (thirteen frames, one transcript) and `prod/DRIFT/` (three transcripts), and replaced stages `02-mcp-servers`, `03-tools`, `04-skills`, `05-sub-agents`, `14-runs-and-ops`, `18-registry-cache-and-retrieval` and `28-config-hardening` with their re-runs on that image. The hardening wave added stage `36-hardening-wave` (eleven frames, one transcript) and `prod/HARDENING/` (three transcripts), and replaced stages `03-tools`, `04-skills`, `05-sub-agents`, `14-runs-and-ops`, `18-registry-cache-and-retrieval`, `28-config-hardening` and `35-schema-drift` with their re-runs on the second-reading image. The third reading added `prod/HARDENING/third-reading.md`, replaced `prod/M56/` (the ceremony and addendum re-run from a fresh volume on the third-reading image, eleven frames), and replaced stages `02-mcp-servers`, `03-tools`, `04-skills`, `05-sub-agents`, `14-runs-and-ops`, `18-registry-cache-and-retrieval`, `27-a2a`, `28-config-hardening`, `35-schema-drift` and `36-hardening-wave` (twelve frames now: the unjudged-save notice) with their re-runs on that image.

The unreferenced-frame count (frames no markdown names) was 729 of 775 at the start: the old campaigns referenced frames by directory listing, not by name. Every frame in the consolidated tree is named by the transcript of the stage or drill that took it — **with one exception, and it is real**: `35-schema-drift/` holds 21 frames while its transcript names 13. `publish.mjs` does replace a stage directory wholesale (`rmSync` then copy), but the *capture* directory it copies from is only ever created, never cleared (`lib.mjs`), and this stage shoots the live schema version into each filename — so a re-run adds a differently-named set beside the previous one in the capture directory and publishes both. The eight left over are

```
01-drawer-schema-v7.png        01-drawer-schema-v9.png
02-trace-tool-call-schema-v7.png   02-trace-tool-call-schema-v9.png
04-drawer-banner-v8.png        04-drawer-banner-v10.png
12-trace-tool-call-schema-v9.png   12-trace-tool-call-schema-v11.png
```

— the hardening-wave and second-reading readings of the same stage, superseded by the third-reading pass whose frames (`…-v3`, `…-v4`, `…-v5`) are the ones the transcript names. They prove nothing the current transcript claims; they are kept here rather than deleted silently, and this note is what the count is. **Unreferenced frames: 8 of 336, all in `35-schema-drift/`.**
