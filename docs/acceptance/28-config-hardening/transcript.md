```
[   0.0s] # 28-config-hardening — 2026-09-11T01:38:00.596Z
[   0.1s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.8s] shot 00-conv-a-pinned.png
[   2.9s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  12.1s] gate approved from the chat card
[  20.1s] run e48de8fa-7589-45d6-901a-20b4d3cf046d → completed after 15s
[  20.3s] run e48de8fa-7589-45d6-901a-20b4d3cf046d → completed after 8s
[  21.5s] run e48de8fa → completed; steps: route::completed skill:direct:completed tool_call:demo-stub_echo:completed tool_call:demo-stub_add:completed route:route:work:completed skill:work:completed tool_call:demo-stub_echo:completed tool_call:demo-stub_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  21.5s] answer: approved 8 + 9 = 17 — the claim checks out; no publish tool is available, so nothing was posted. The claim "8 and 9 make seventeen" checks out (8 + 9 = 17), so 
[  21.5s] conversation A run: target=site-analyst (direct) status=completed
[  21.6s] shot 01-conv-a-direct-run.png
[  22.5s] conversation B picker:  (empty = Orchestrator (auto))
[  22.6s] shot 02-conv-b-picker-auto.png
[  22.7s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  41.9s] run 7945897b-90c9-4dfb-ab07-c7fb7fc8808b → completed after 17s
[  41.9s] run 7945897b-90c9-4dfb-ab07-c7fb7fc8808b → completed after 0s
[  43.1s] run 7945897b → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  43.1s] answer: 7
[  43.1s] conversation B run: target=orchestrator status=completed
[  43.3s] shot 03-conv-b-planner-run.png
[  45.3s] back in A: pin restored=true
[  45.4s] history-summary option shown for the pinned conversation and checked
[  45.5s] shot 04-conv-a-pin-restored-summary-checked.png
[  47.3s] back in B: picker=auto
[  47.5s] shot 05-conv-b-still-auto.png
[  49.4s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  62.9s] gate approved from the chat card
[  70.7s] run 9cba84ac-852e-408f-8343-4dba9f666671 → completed after 19s
[  71.0s] run 9cba84ac-852e-408f-8343-4dba9f666671 → completed after 8s
[  72.2s] run 9cba84ac → completed; steps: route::completed summary::completed skill:direct:completed tool_call:demo-stub_echo:completed tool_call:demo-stub_add:completed route:route:work:completed skill:work:completed tool_call:demo-stub_add:completed tool_call:demo-stub_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  72.2s] answer: approved 20 + 22 = 42, so the statement "20 and 22 make forty-two" is correct — but no publish tool is available, so nothing was posted. 20 + 22 = 42, so the st
[  72.2s] conversation A second run: target=direct include_history_summary=true
[  72.3s] shot 06-conv-a-second-direct-plus-ctx.png
[  74.2s] shot 09-settings-ambient-knobs.png
[  75.2s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[  75.4s] shot 10-settings-tick-45-readback.png
[  76.6s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[  76.7s] shot 11-settings-422-inline.png
[  78.1s] shot 12-settings-a2a-on-knobs.png
[  78.6s] shot 13-settings-api-guardrails.png
[  79.0s] shot 14-settings-orchestrator-overlap-recursion.png
[  79.1s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[  81.1s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 126.7s] run db9b4c16-db28-45e2-86be-93011b2dffff → completed after 44s
[ 127.9s] run db9b4c16 → completed; steps: plan::completed route::completed skill::completed tool_call:polyglot-agent_research:completed aggregate::completed
[ 127.9s] answer: The request was sent to the remote polyglot agent to research tick-bounded polling, but it did not return within the short inline window, so it was left running
[ 127.9s] parked: false
[ 128.0s] shot 15-poll-throttle-parked-answer.png
[ 158.1s] after 30s with poll=5s but tick=60s: this run's task completed/delivered (effective cadence is max(tick, interval))
[ 160.8s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 161.3s] settings ← {"ambient_tick_interval_s":15}
[ 161.3s] tick lowered to 15s → delivered within 2 minutes: true
[ 162.5s] shot 17-poll-interval-lowered-task-delivered.png
[ 165.8s] shot 18-poll-inbox-delivery.png
[ 165.9s] settings ← {"overlap_threshold_percent":10}
[ 168.6s] shot 19-overlap-near-duplicate-form.png
[ 177.3s] overlap judge flagged the save — dialog shown
[ 177.5s] shot 20-overlap-dialog-at-threshold-10.png
[ 178.0s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 178.4s] settings ← {"overlap_threshold_percent":1}
[ 180.1s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 180.2s] shot 21-guardrails-burst-5.png
[ 180.2s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 181.9s] shot 23-ambient-toast-before.png
[ 182.1s] tier-0 delivery seeded server-side: a648e23e-5318-4a82-bc26-cb317a86314f
[ 201.0s] toast: ambient interrupt · ops×payments-api p99 error rate 9.4% and rising
[ 201.1s] shot 24-ambient-toast-visible.png
[ 201.2s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":60,"a2a_task_timeout_s":120,"ambient_quiet_hours":[]}
[ 203.9s] ambient off → nav Ambient links: 0
[ 204.0s] shot 07-settings-ambient-master-off.png
[ 205.0s] ambient on → nav Ambient links: 1
[ 205.2s] shot 08-settings-ambient-on-nav-live.png
[ 205.2s] note: this off/on once stalled the leader tick until a restart (report.md finding 2, fixed — prod/FIXES/ambient-toggle.md re-verifies it); nothing in this stage depends on the tick afterwards
[ 205.2s] # end — 2026-09-11T01:41:25.765Z
```
