```
[   0.0s] # 11-hitl-deny-and-queue — 2026-09-10T02:54:15.159Z
[   0.0s] settings ← {"orchestrator_mode":"graph"}
[   2.0s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  19.6s] shot 00-gate-armed.png
[  22.0s] shot 03-queue-pending.png (second tab)
[  22.1s] approved from the Settings HITL queue (second tab)
[  56.6s] run 7d3a0b2d-d9c7-4dc9-8f8b-48cf0fa8ade9 → completed after 35s
[  58.0s] shot 04-queue-approved-run-completed.png (second tab)
[  58.0s] run 1 → completed after the queue approval
[  58.5s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  76.4s] shot 05-deny-note-typed.png
[  76.5s] denied from the chat card with a note
[  89.7s] run 90c51430-e0a2-483a-b71e-accd80cd533c → completed after 13s
[  91.4s] shot 06-denied-rail-state.png
[  91.4s] run 2 → completed; hitl step: {"note":"Do not publish — the source is a demo page, not a real site.","status":"denied","node_type":"hitl"}; steps: plan::completed route::completed skill:s1:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed hitl:approve:completed route:route:approve:completed aggregate::completed
[  94.3s] shot 07-trace-hitl-decision-deny.png
[  94.8s] # end — 2026-09-10T02:55:49.920Z
```
