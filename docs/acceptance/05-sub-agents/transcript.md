```
[   0.0s] # 05-sub-agents — 2026-09-11T01:32:15.916Z
[   4.3s] shot 00-builder-error-edge.png
[  14.1s] overlap judge flagged the save — dialog shown
[  14.6s] save refused → workflow must have exactly one START edge (found 2)
[  14.6s] create with a dangling edge → error: workflow must have exactly one START edge (found 2)
[  14.8s] shot 01-validation-rejected.png
[  25.8s] overlap judge flagged the save — dialog shown
[  26.1s] shot 01a-overlap-dialog.png
[  26.6s] create → {"outcome":"saved","text":"","sawOverlap":true}
[  26.6s] saved: site-analyst nodes=work:skill,approve:hitl,finish:skill,recover:skill edges=6
[  27.2s] shot 02-site-analyst-saved.png
[  28.3s] shot 03-static-seed-card-drawer.png
[  31.4s] shot 04-dag-preview-rendered.png
[  35.6s] delete bound skill → skill is referenced by active sub agents: site-analyst, site-reporter
[  35.7s] shot 05-skill-delete-conflict.png
[  36.2s] # end — 2026-09-11T01:32:52.081Z
```
