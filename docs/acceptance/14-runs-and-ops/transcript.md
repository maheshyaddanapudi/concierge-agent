<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `ab07205`** (the third-reading build) — **2 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: C — the hardening wave moved what this page claims**
> `RunsPage.tsx`, `api/runs.py`, `obs.py` (+95) and `seed/loader.py` (+68/−5) all moved — the runs list, the observability controls and the seed reload are three of this stage's six frames.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 14-runs-and-ops — 2026-09-11T22:37:06.433Z
[   1.7s] runs listed: 20 (completed, cancelled, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, failed, cancelled, completed, completed, completed, completed, completed)
[   1.9s] shot 00-runs-list.png
[   3.3s] shot 01-trace-drawer-answer-and-artifact.png
[   4.0s] shot 02-step-timeline.png
[   5.3s] search "summary" → 3 rows
[   5.4s] shot 03-runs-search-filter.png
[   7.7s] shot 04-observability-controls.png
[   7.8s] directly exposed capabilities: 3; cap warning before: 10
[   9.1s] cap warning now: 1
[  10.6s] banner: ⚠ 3 capabilities are directly exposed to the orchestrator (warning threshold 1). Every exposure adds planner context cost — prefer progressive disclosure throug
[  10.8s] shot 05-exposure-cap-banner-tools.png
[  10.8s] settings ← {"direct_exposure_cap_warning":10}
[  15.5s] seed reload → tools 37→37, skills 9→9, ids unchanged
[  15.7s] shot 06-after-seed-reload.png
[  15.7s] # end — 2026-09-11T22:37:22.103Z
```
