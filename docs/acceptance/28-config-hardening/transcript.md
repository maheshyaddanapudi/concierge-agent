```
[   0.0s] # 28-config-hardening — 2026-09-11T22:48:02.758Z
[   0.1s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.8s] shot 00-conv-a-pinned.png
[   2.9s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  13.8s] gate approved from the chat card
[  20.9s] run fd02ec3e-2d41-4b09-b8a3-101779bf2204 → completed after 7s
[  21.1s] run fd02ec3e-2d41-4b09-b8a3-101779bf2204 → completed after 16s
[  22.1s] run fd02ec3e → completed; steps: route::completed skill:direct:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  22.1s] answer: approved The claim checks out: 8 + 9 = 17. Correct: 8 + 9 = 17.
[  22.1s] conversation A run: target=site-analyst (direct) status=completed
[  22.3s] shot 01-conv-a-direct-run.png
[  23.1s] conversation B picker:  (empty = Orchestrator (auto))
[  23.2s] shot 02-conv-b-picker-auto.png
[  23.3s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  48.6s] run e27140c2-e2c7-41b7-a2fe-15e956411db6 → completed after 23s
[  48.6s] run e27140c2-e2c7-41b7-a2fe-15e956411db6 → completed after 0s
[  49.8s] run e27140c2 → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  49.8s] answer: 7
[  49.8s] conversation B run: target=orchestrator status=completed
[  50.0s] shot 03-conv-b-planner-run.png
[  52.0s] back in A: pin restored=true
[  52.1s] history-summary option shown for the pinned conversation and checked
[  52.2s] shot 04-conv-a-pin-restored-summary-checked.png
[  54.1s] back in B: picker=auto
[  54.2s] shot 05-conv-b-still-auto.png
[  56.1s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  70.2s] gate approved from the chat card
[  81.4s] run c6ced4a6-7518-43b3-b34f-66ef0ec8cba0 → completed after 11s
[  81.5s] run c6ced4a6-7518-43b3-b34f-66ef0ec8cba0 → completed after 23s
[  82.6s] run c6ced4a6 → completed; steps: route::completed summary::completed skill:direct:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  82.6s] answer: approved 20 + 22 = 42, so "20 and 22 make forty-two" is correct — published. Published: 20 + 22 = 42, so "20 and 22 make forty-two" is correct and approved.
[  82.6s] conversation A second run: target=direct include_history_summary=true
[  82.7s] shot 06-conv-a-second-direct-plus-ctx.png
[  84.6s] shot 09-settings-ambient-knobs.png
[  85.6s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[  85.8s] shot 10-settings-tick-45-readback.png
[  87.0s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[  87.2s] shot 11-settings-422-inline.png
[  88.5s] shot 12-settings-a2a-on-knobs.png
[  89.0s] shot 13-settings-api-guardrails.png
[  89.5s] shot 14-settings-orchestrator-overlap-recursion.png
[  89.6s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[  91.7s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 174.8s] run 86fd6aad-7f10-49bd-924f-caccd7ea0d4b → completed after 81s
[ 176.0s] run 86fd6aad → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research-34b327:completed tool_call:polyglot-agent_research-34b327:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 176.0s] answer: The remote polyglot agent did not return research findings on tick-bounded polling before the wait limit, so I did not wait. The only response was a status note
[ 176.0s] parked: true
[ 176.1s] shot 15-poll-throttle-parked-answer.png
[ 206.2s] after 30s with poll=5s but tick=60s: this run's task parked, completed/delivered (effective cadence is max(tick, interval))
[ 209.0s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 209.4s] settings ← {"ambient_tick_interval_s":15}
[ 209.4s] tick lowered to 15s → delivered within 2 minutes: true
[ 210.6s] shot 17-poll-interval-lowered-task-delivered.png
[ 214.0s] shot 18-poll-inbox-delivery.png
[ 214.0s] settings ← {"overlap_threshold_percent":10}
[ 216.8s] shot 19-overlap-near-duplicate-form.png
[ 225.0s] overlap judge flagged the save — dialog shown
[ 225.3s] shot 20-overlap-dialog-at-threshold-10.png
[ 225.8s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 226.3s] settings ← {"overlap_threshold_percent":1}
[ 227.9s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 228.1s] shot 21-guardrails-burst-5.png
[ 228.1s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 229.8s] shot 23-ambient-toast-before.png
[ 229.9s] tier-0 delivery seeded server-side: 9b15cec2-cf17-4be9-82f4-457ac1975d98
[ 241.8s] toast: ambient interrupt · ops×payments-api p99 error rate 9.4% and rising
[ 242.0s] shot 24-ambient-toast-visible.png
[ 242.0s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[ 244.7s] ambient off → nav Ambient links: 0
[ 244.8s] shot 07-settings-ambient-master-off.png
[ 245.8s] ambient on → nav Ambient links: 1
[ 246.0s] shot 08-settings-ambient-on-nav-live.png
[ 246.0s] note: this off/on once stalled the leader tick until a restart (report.md finding 2, fixed — prod/FIXES/ambient-toggle.md re-verifies it); nothing in this stage depends on the tick afterwards
[ 246.0s] # end — 2026-09-11T22:52:08.733Z
```
