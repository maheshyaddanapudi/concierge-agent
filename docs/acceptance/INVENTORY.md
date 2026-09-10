# Acceptance evidence inventory (campaign acceptance_v1)

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
| `27-a2a` | 40 | 40 | 5ec9e77 2026-08-28 | stage 27-a2a | pending |
| `28-config-hardening` | 25 | 24 | 783643e 2026-08-28 | stage 28-config-hardening | pending |
| `29-ambient-pursuit` | 4 | 3 | 9720be8 2026-08-28 | stage 29-ambient-pursuit | pending |
| `30-salience` | 14 | 11 | 4fb2b8a 2026-08-29 | stage 30-salience | pending |
| `31-salience-decisions` | 15 | 12 | 5bab618 2026-08-30 | stage 31-salience-decisions | pending |
| `32-durable-forgetting` | 14 | 10 | 915ced7 2026-08-30 | stage 32-durable-forgetting | pending |
| `(root)` | 4 | 0 | e71305a 2026-09-10 | campaign (root) | pending |
| `a2a-14d` | 46 | 39 | 5ec9e77 2026-08-28 | spec §14d steps 33–40 on five scripted counterparties | pending |
| `ambient_channels_m29` | 3 | 2 | ae68c1e 2026-08-25 | campaign ambient_channels_m29 | pending |
| `ambient_m23` | 7 | 6 | 5ab6f69 2026-08-25 | campaign ambient_m23 | pending |
| `ambient_m25` | 2 | 1 | 7e261f7 2026-08-25 | campaign ambient_m25 | pending |
| `ambient_ui_m30` | 11 | 10 | aa13608 2026-08-25 | campaign ambient_ui_m30 | pending |
| `archive` | 334 | 326 | 5ec9e77 2026-08-28 | earlier campaigns superseded by the ones above (walkone retest, first campaign frames) | pending |
| `auth_m34` | 6 | 4 | 0da8f60 2026-08-26 | campaign auth_m34 | pending |
| `ceremony_m36` | 68 | 66 | a404e64 2026-08-26 | the M36 full acceptance ceremony (spec §18.10) | pending |
| `coordination_m35` | 1 | 0 | d0ab4c0 2026-08-26 | campaign coordination_m35 | pending |
| `evals_m32` | 4 | 3 | 4537a6e 2026-08-25 | campaign evals_m32 | pending |
| `prod` | 94 | 31 | ae19740 2026-09-10 | the production-hardening drills M49–M56 | pending |

Totals: 879 assets, 775 frames, 133 MB.

The unreferenced-frame count (frames no markdown names) was 729 of 775 at the start: the old campaigns referenced frames by directory listing, not by name. The consolidated index references every frame it keeps by name, so this number ends at zero.
