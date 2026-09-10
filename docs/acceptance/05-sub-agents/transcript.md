```
[   0.0s] # 05-sub-agents — 2026-09-10T02:43:22.611Z
[   4.3s] shot 00-builder-error-edge.png
[  15.9s] overlap judge flagged the save — dialog shown
[  16.4s] save refused → workflow must have exactly one START edge (found 2)
[  16.4s] create with a dangling edge → error: workflow must have exactly one START edge (found 2)
[  16.5s] shot 01-validation-rejected.png
[  36.6s] overlap judge flagged the save — dialog shown
[  37.1s] shot 01a-overlap-dialog.png
[  37.6s] create → {"outcome":"saved","text":"","sawOverlap":true}
[  37.6s] saved: site-analyst nodes=work:skill,approve:hitl,finish:skill,recover:skill edges=6
[  38.2s] shot 02-site-analyst-saved.png
[  39.3s] shot 03-static-seed-card-drawer.png
[  42.5s] shot 04-dag-preview-rendered.png
[  46.6s] delete bound skill → skill is referenced by active sub agents: site-analyst
[  46.7s] shot 05-skill-delete-conflict.png
[  47.2s] # end — 2026-09-10T02:44:09.799Z
```
