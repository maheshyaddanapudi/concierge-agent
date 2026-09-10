```
[   0.0s] # 28-config-hardening — 2026-09-10T19:39:43.163Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.6s] shot 00-conv-a-pinned.png
[   2.7s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  12.2s] gate approved from the chat card
[  29.0s] run ba7b8903-e864-4c23-9bdb-e8c322ba5b90 → completed after 24s
[  29.4s] run ba7b8903-e864-4c23-9bdb-e8c322ba5b90 → completed after 17s
[  30.6s] run ba7b8903 → completed; steps: route::completed skill:direct:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  30.6s] answer: approved Summary: 8 + 9 = 17, so the statement is correct (approved); no publish tool is available here, so nothing was actually published. 8 + 9 = 17 — the sta
[  30.6s] conversation A run: target=site-analyst (direct) status=completed
[  30.8s] shot 01-conv-a-direct-run.png
[  31.6s] conversation B picker:  (empty = Orchestrator (auto))
[  31.8s] shot 02-conv-b-picker-auto.png
[  31.8s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  56.2s] run d8c37ab4-726c-49a6-9de6-e8ff731348a6 → completed after 22s
[  56.2s] run d8c37ab4-726c-49a6-9de6-e8ff731348a6 → completed after 0s
[  57.4s] run d8c37ab4 → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  57.4s] answer: 7
[  57.4s] conversation B run: target=orchestrator status=completed
[  57.5s] shot 03-conv-b-planner-run.png
[  59.6s] back in A: pin restored=true
[  59.6s] history-summary option shown for the pinned conversation and checked
[  59.8s] shot 04-conv-a-pin-restored-summary-checked.png
[  61.6s] back in B: picker=auto
[  61.7s] shot 05-conv-b-still-auto.png
[  63.6s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  79.1s] gate approved from the chat card
[  96.1s] run fbca1f91-8cc8-48ec-bf44-80ab8473f65f → completed after 30s
[  96.4s] run fbca1f91-8cc8-48ec-bf44-80ab8473f65f → completed after 17s
[  97.6s] run fbca1f91 → completed; steps: route::completed summary::completed skill:direct:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  97.6s] answer: approved 20 + 22 = 42 — the claim "20 and 22 make forty-two" is arithmetically correct, and no publish tool is available, so nothing was published. Summary: 20 
[  97.6s] conversation A second run: target=direct include_history_summary=true
[  97.8s] shot 06-conv-a-second-direct-plus-ctx.png
[ 100.5s] ambient off → nav Ambient links: 0
[ 100.6s] shot 07-settings-ambient-master-off.png
[ 101.7s] ambient on → nav Ambient links: 1
[ 101.8s] shot 08-settings-ambient-on-nav-live.png
[ 102.0s] shot 09-settings-ambient-knobs.png
[ 103.0s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[ 103.2s] shot 10-settings-tick-45-readback.png
[ 104.4s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[ 104.5s] shot 11-settings-422-inline.png
[ 105.8s] shot 12-settings-a2a-on-knobs.png
[ 106.3s] shot 13-settings-api-guardrails.png
[ 106.8s] shot 14-settings-orchestrator-overlap-recursion.png
[ 106.8s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[ 108.9s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 303.6s] run 36935c3f-ab59-4739-a7c0-efc0149e703f → completed after 193s
[ 304.8s] run 36935c3f → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 304.8s] answer: The remote polyglot agent did **not** return substantive research on **tick-bounded polling** within the non-blocking window. What came back was only a parked/i
[ 304.8s] parked: true
[ 304.9s] shot 15-poll-throttle-parked-answer.png
[ 335.0s] after 30s with poll=5s but tick=60s: task states completed, completed, completed, input-required, input-required, completed, completed, completed, canceled, input-required, input-required, completed, completed, completed, completed (effective cadence is max(tick, interval))
[ 337.7s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 338.2s] settings ← {"ambient_tick_interval_s":15}
[ 338.2s] tick lowered to 15s → delivered within 2 minutes: true
[ 339.4s] shot 17-poll-interval-lowered-task-delivered.png
[ 342.7s] shot 18-poll-inbox-delivery.png
[ 342.8s] settings ← {"overlap_threshold_percent":10}
[ 345.5s] shot 19-overlap-near-duplicate-form.png
[ 352.1s] overlap judge flagged the save — dialog shown
[ 352.4s] shot 20-overlap-dialog-at-threshold-10.png
[ 352.9s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 353.3s] settings ← {"overlap_threshold_percent":1}
[ 355.1s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 355.2s] shot 21-guardrails-burst-5.png
[ 355.2s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 356.9s] shot 23-ambient-toast-before.png
[ 357.0s] tier-0 delivery seeded server-side: 10cd0273-c639-4f98-9de2-d7182b5bee48
[ 389.1s] toast: ambient interrupt · ops×payments-api p99 error rate 9.4% and rising
[ 389.3s] shot 24-ambient-toast-visible.png
[ 389.3s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":60,"a2a_task_timeout_s":120,"ambient_quiet_hours":[]}
[ 389.3s] # end — 2026-09-10T19:46:12.448Z
```
