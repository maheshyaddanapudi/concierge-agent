```
[   0.0s] # 28-config-hardening — 2026-09-10T20:38:44.301Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.6s] shot 00-conv-a-pinned.png
[   2.7s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  12.3s] gate approved from the chat card
[  31.1s] run 2ef3870b-697a-4426-bf07-6b2f59a356e7 → completed after 26s
[  31.6s] run 2ef3870b-697a-4426-bf07-6b2f59a356e7 → completed after 19s
[  32.8s] run 2ef3870b → completed; steps: route::completed skill:direct:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  32.8s] answer: approved 8 + 9 = 17 — the claim is correct; summary delivered here since no publish tool is available. The claim checks out: 8 + 9 = 17. (No publish tool is ava
[  32.8s] conversation A run: target=site-analyst (direct) status=completed
[  33.0s] shot 01-conv-a-direct-run.png
[  33.8s] conversation B picker:  (empty = Orchestrator (auto))
[  34.0s] shot 02-conv-b-picker-auto.png
[  34.0s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  57.4s] run 692c69be-6461-4888-86b4-98321d18a915 → completed after 21s
[  57.4s] run 692c69be-6461-4888-86b4-98321d18a915 → completed after 0s
[  58.6s] run 692c69be → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  58.6s] answer: 7
[  58.6s] conversation B run: target=orchestrator status=completed
[  58.7s] shot 03-conv-b-planner-run.png
[  60.8s] back in A: pin restored=true
[  60.8s] history-summary option shown for the pinned conversation and checked
[  60.9s] shot 04-conv-a-pin-restored-summary-checked.png
[  62.8s] back in B: picker=auto
[  62.9s] shot 05-conv-b-still-auto.png
[  64.8s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  77.3s] gate approved from the chat card
[  91.2s] run 9101acd5-b124-4144-a7cc-3fa2fc2ed66e → completed after 24s
[  91.8s] run 9101acd5-b124-4144-a7cc-3fa2fc2ed66e → completed after 14s
[  93.0s] run 9101acd5 → completed; steps: route::completed summary::completed skill:direct:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  93.0s] answer: approved Claim verified: 20 + 22 = 42, so the statement is correct — no publish tool is available here, so this summary is delivered inline. Claim verified: 20 
[  93.0s] conversation A second run: target=direct include_history_summary=true
[  93.2s] shot 06-conv-a-second-direct-plus-ctx.png
[  95.0s] shot 09-settings-ambient-knobs.png
[  96.1s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[  96.2s] shot 10-settings-tick-45-readback.png
[  97.5s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[  97.6s] shot 11-settings-422-inline.png
[  98.9s] shot 12-settings-a2a-on-knobs.png
[  99.4s] shot 13-settings-api-guardrails.png
[  99.9s] shot 14-settings-orchestrator-overlap-recursion.png
[  99.9s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[ 102.0s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 218.7s] run 8176b1a9-bded-47a9-8c12-ce036dff497a → completed after 115s
[ 219.8s] run 8176b1a9 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 219.8s] answer: No substantive research on tick-bounded polling was returned. Within the short non-blocking window, the remote polyglot agent only reported that it was still wo
[ 219.9s] parked: true
[ 220.0s] shot 15-poll-throttle-parked-answer.png
[ 250.0s] after 30s with poll=5s but tick=60s: this run's task completed/delivered, completed/delivered (effective cadence is max(tick, interval))
[ 252.8s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 253.3s] settings ← {"ambient_tick_interval_s":15}
[ 253.3s] tick lowered to 15s → delivered within 2 minutes: true
[ 254.5s] shot 17-poll-interval-lowered-task-delivered.png
[ 257.8s] shot 18-poll-inbox-delivery.png
[ 257.9s] settings ← {"overlap_threshold_percent":10}
[ 260.6s] shot 19-overlap-near-duplicate-form.png
[ 267.3s] overlap judge flagged the save — dialog shown
[ 267.6s] shot 20-overlap-dialog-at-threshold-10.png
[ 268.1s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 268.5s] settings ← {"overlap_threshold_percent":70}
[ 270.2s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 270.3s] shot 21-guardrails-burst-5.png
[ 270.4s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 272.1s] shot 23-ambient-toast-before.png
[ 272.2s] tier-0 delivery seeded server-side: 58744a59-d927-43eb-9e5f-ba694b021681
[ 280.6s] toast: ambient interrupt · ops×payments-api p99 error rate 9.4% and rising
[ 280.8s] shot 24-ambient-toast-visible.png
[ 280.8s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":60,"a2a_task_timeout_s":120,"ambient_quiet_hours":["22:14","22:44"]}
[ 283.5s] ambient off → nav Ambient links: 0
[ 283.6s] shot 07-settings-ambient-master-off.png
[ 284.7s] ambient on → nav Ambient links: 1
[ 284.8s] shot 08-settings-ambient-on-nav-live.png
[ 284.8s] note: after this off/on the leader tick may stall until the backend restarts (report.md finding 2) — nothing below depends on it
[ 284.8s] # end — 2026-09-10T20:43:29.107Z
```
