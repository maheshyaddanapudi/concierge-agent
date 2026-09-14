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
> `answer_ui.py` (+81/−18), `AnswerPanel.tsx` and `ChartSvg.tsx` (+217/−90) are the formatter this stage photographs in four modes.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 24-formatter — 2026-09-10T03:33:24.498Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"formatter_enabled":true,"formatter_presentation":"a2ui_first"}
[   2.9s] shot 00-settings-on-a2ui-first.png
[   3.8s] presentation → raw_first
[   5.8s] UI send: Add 21 and 21 and present the result as a short report: a heading, one stat, and
[  17.9s] run 711f22be-7dbd-434d-b23c-fccd8c9a37bb → completed after 10s
[  17.9s] run 711f22be-7dbd-434d-b23c-fccd8c9a37bb → completed after 0s
[  19.1s] run 711f22be → completed; steps: plan::completed
[  19.1s] answer: # Sum Report: 21 + 21 - **Total:** 42 Adding 21 and 21 yields a sum of 42.
[  19.3s] shot 01-raw-first-primary.png
[  20.1s] shot 02-raw-first-structured-expanded.png
[  20.1s] raw-first run answer_ui present: true; components: 2
[  23.1s] formatter_enabled → false; presentation options rendered: 0
[  23.3s] shot 03-settings-off-options-hidden.png
[  25.3s] UI send: Add 30 and 12 and present the result as a short report: a heading, one stat, and
[  36.4s] run b531a2fd-9cfe-4e4a-a360-f0e4acc4d8e6 → completed after 9s
[  36.4s] run b531a2fd-9cfe-4e4a-a360-f0e4acc4d8e6 → completed after 0s
[  37.6s] run b531a2fd → completed; steps: plan::completed
[  37.6s] answer: ## Sum Report: 30 + 12 **Total: 42** Adding 30 and 12 yields 42.
[  37.6s] formatter off: answer_ui=null; toggles on the page: 0
[  37.8s] shot 04-off-raw-only-no-toggle.png
[  37.8s] settings ← {"formatter_enabled":true,"formatter_presentation":"a2ui_first"}
[  40.6s] history after the flip back: raw-first conversation shows the structured-summary toggle: 1 (presentation frozen per run)
[  40.7s] shot 05-history-immutable-after-flip.png
[  40.7s] # end — 2026-09-10T03:34:05.244Z
```
