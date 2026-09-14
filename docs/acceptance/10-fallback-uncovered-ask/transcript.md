<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `b624908`** (release 1.0.0 / M1–M56 — the campaign build) — **6 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: C — the hardening wave moved what this page claims**
> This stage's whole subject is the full-catalog fallback rung. `prompts/fallback.md` is one of three prompt files the wave ADDED (+30 lines) and `ladder.py` was rewritten (+85/−9).
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 10-fallback-uncovered-ask — 2026-09-10T02:52:56.948Z
[   0.1s] settings ← {"orchestrator_mode":"graph","default_model_params":null}
[   2.3s] UI send: Use the invoice-reconciler capability to reconcile last month's supplier invoice
[   7.1s] fallback banner live
[   7.2s] shot 00-fallback-banner-live.png
[  73.1s] run b37f4948-db78-4abd-8373-47cf4d918d0c → completed after 66s
[  74.8s] shot 01-fallback-answer.png
[  74.8s] plan.no_confident_match=true route.rung=fallback; steps: plan::completed route::completed skill::completed tool_call:filesystem_list_allowed_directories:completed tool_call:memory_recall:completed tool_call:filesystem_directory_tree:completed tool_call:filesystem_search_files:completed aggregate::completed
[  74.8s] answer: I couldn’t complete the invoice reconciliation or list mismatches.

Concrete findings:

- The requested `invoice-reconciler` functionality is not available in t
[  77.8s] shot 02-trace-rung-fallback.png
[  78.2s] # end — 2026-09-10T02:54:15.158Z
```
