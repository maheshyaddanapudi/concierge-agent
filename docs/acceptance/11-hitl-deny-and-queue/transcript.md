```
[   0.0s] # 11-hitl-deny-and-queue — 2026-09-10T23:42:19.596Z
[   0.1s] settings ← {"orchestrator_mode":"graph"}
[   2.3s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  55.8s] shot 00-gate-armed.png
[  58.1s] shot 03-queue-pending.png (second tab)
[  58.2s] approved from the Settings HITL queue (second tab)
[ 121.1s] run 6ef33d9d-8788-4536-9830-b92045d661d8 → completed after 63s
[ 122.4s] shot 04-queue-approved-run-completed.png (second tab)
[ 122.5s] run 1 → completed after the queue approval
[ 122.9s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[ 151.0s] shot 05-deny-note-typed.png
[ 151.0s] denied from the chat card with a note
[ 164.2s] run c66ebf23-34b4-48aa-a1c2-dd6c9d07cd27 → completed after 13s
[ 165.8s] shot 06-denied-rail-state.png
[ 165.8s] run 2 → completed; hitl step: {"note":"Do not publish — the source is a demo page, not a real site.","status":"denied","node_type":"hitl"}; steps: plan::completed route::completed skill:s1:completed tool_call:demo-stub_echo:completed tool_call:demo-stub_add:completed route:route:sum:completed skill:sum:completed hitl:approve:completed route:route:approve:completed aggregate::completed
[ 168.9s] shot 07-trace-hitl-decision-deny.png
[ 169.3s] # end — 2026-09-10T23:45:08.929Z
```
