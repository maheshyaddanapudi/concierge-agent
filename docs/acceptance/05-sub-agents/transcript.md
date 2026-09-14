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
> `03-static-seed-card-drawer.png` shows the static sub-agent drawer — exactly where the wave added the Status toggle that the page claimed in its own copy and never rendered. The drawer in this frame is missing a control HEAD draws.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 05-sub-agents — 2026-09-11T22:36:30.119Z
[   4.5s] shot 00-builder-error-edge.png
[  13.9s] overlap judge flagged the save — dialog shown
[  14.5s] save refused → workflow must have exactly one START edge (found 2)
[  14.5s] create with a dangling edge → error: workflow must have exactly one START edge (found 2)
[  14.6s] shot 01-validation-rejected.png
[  25.3s] overlap judge flagged the save — dialog shown
[  25.6s] shot 01a-overlap-dialog.png
[  26.2s] create → {"outcome":"saved","text":"","sawOverlap":true}
[  26.2s] saved: site-analyst nodes=work:skill,approve:hitl,finish:skill,recover:skill edges=6
[  26.7s] shot 02-site-analyst-saved.png
[  27.8s] shot 03-static-seed-card-drawer.png
[  30.9s] shot 04-dag-preview-rendered.png
[  35.0s] delete bound skill → skill is referenced by active sub agents: site-analyst
[  35.2s] shot 05-skill-delete-conflict.png
[  35.6s] # end — 2026-09-11T22:37:05.763Z
```
