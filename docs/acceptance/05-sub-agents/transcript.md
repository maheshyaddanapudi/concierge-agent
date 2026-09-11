```
[   0.0s] # 05-sub-agents — 2026-09-11T21:31:22.005Z
[   4.1s] shot 00-builder-error-edge.png
[  16.4s] overlap judge flagged the save — dialog shown
[  16.9s] save refused → workflow must have exactly one START edge (found 2)
[  16.9s] create with a dangling edge → error: workflow must have exactly one START edge (found 2)
[  17.1s] shot 01-validation-rejected.png
[  30.2s] overlap judge flagged the save — dialog shown
[  30.6s] shot 01a-overlap-dialog.png
[  31.1s] create → {"outcome":"saved","text":"","sawOverlap":true}
[  31.1s] saved: site-analyst nodes=work:skill,approve:hitl,finish:skill,recover:skill edges=6
[  31.6s] shot 02-site-analyst-saved.png
[  32.7s] shot 03-static-seed-card-drawer.png
[  35.8s] shot 04-dag-preview-rendered.png
[  40.0s] delete bound skill → skill is referenced by active sub agents: site-analyst
[  40.1s] shot 05-skill-delete-conflict.png
[  40.6s] # end — 2026-09-11T21:32:02.561Z
```
