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
> **The sharpest mismatch in the tree.** This transcript records `static skill file-ops: … live switches: 1`. The wave added the Status toggle that `SkillsPage` and `SubAgentsPage` claimed and never rendered, so HEAD shows TWO live switches where `00-static-skill-drawer.png` shows one. This page documents the defect as though it were the proof of the rule.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 15-static-guards — 2026-09-10T03:02:31.517Z
[   2.6s] static skill file-ops: fields 39/39 disabled, Delete buttons: 0, live switches: 1
[   2.8s] shot 00-static-skill-drawer.png
[   5.7s] static server fetch: fields 0/0 disabled, Delete buttons: 0, live switches: 0
[   5.9s] shot 01-static-server-drawer-no-delete.png
[   9.5s] native static tool ambient.wakeup: fields 1/1 disabled, Delete buttons: 0, live switches: 2
[   9.6s] shot 02-native-static-tool-drawer.png
[  10.1s] # end — 2026-09-10T03:02:41.603Z
```
