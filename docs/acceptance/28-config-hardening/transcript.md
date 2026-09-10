```
[   0.0s] # 28-config-hardening — 2026-09-10T20:07:14.929Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.6s] shot 00-conv-a-pinned.png
[   2.7s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  10.9s] gate approved from the chat card
[  27.2s] run 9d413e71-9d44-45ef-85a1-30834b05f21e → completed after 16s
[  28.1s] run 9d413e71-9d44-45ef-85a1-30834b05f21e → completed after 23s
[  28.4s] run 9d413e71 → completed; steps: route::completed skill:direct:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  28.4s] answer: approved Summary: 8 + 9 = 17, so the claim "seventeen" is correct; note that no publish/sitefiles-upload tool is available here, so the summary can only be echo
[  28.4s] conversation A run: target=site-analyst (direct) status=completed
[  28.5s] shot 01-conv-a-direct-run.png
[  29.4s] conversation B picker:  (empty = Orchestrator (auto))
[  29.5s] shot 02-conv-b-picker-auto.png
[  29.6s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  53.9s] run 4f477bd5-996c-4425-ae9c-b6f888c1be86 → completed after 22s
[  54.0s] run 4f477bd5-996c-4425-ae9c-b6f888c1be86 → completed after 0s
[  55.2s] run 4f477bd5 → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  55.2s] answer: 7
[  55.2s] conversation B run: target=orchestrator status=completed
[  55.3s] shot 03-conv-b-planner-run.png
[  57.4s] back in A: pin restored=true
[  57.4s] history-summary option shown for the pinned conversation and checked
[  57.5s] shot 04-conv-a-pin-restored-summary-checked.png
[  59.4s] back in B: picker=auto
[  59.5s] shot 05-conv-b-still-auto.png
[  61.4s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  78.5s] gate approved from the chat card
[  94.7s] run 321c9335-ea35-4217-a51e-28d46906a8cf → completed after 16s
[  94.9s] run 321c9335-ea35-4217-a51e-28d46906a8cf → completed after 31s
[  95.9s] run 321c9335 → completed; steps: route::completed summary::completed skill:direct:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed route:route:work:completed skill:work:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  95.9s] answer: approved 20 + 22 = 42 — the claim is correct, but no publish tool exists, so it can only be echoed, not published. 20 + 22 = 42 — claim correct, but no publish 
[  95.9s] conversation A second run: target=direct include_history_summary=true
[  96.1s] shot 06-conv-a-second-direct-plus-ctx.png
[  98.8s] ambient off → nav Ambient links: 0
[  98.9s] shot 07-settings-ambient-master-off.png
[ 100.0s] ambient on → nav Ambient links: 1
[ 100.1s] shot 08-settings-ambient-on-nav-live.png
[ 100.3s] shot 09-settings-ambient-knobs.png
[ 101.4s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[ 101.5s] shot 10-settings-tick-45-readback.png
[ 102.8s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[ 102.9s] shot 11-settings-422-inline.png
[ 104.3s] shot 12-settings-a2a-on-knobs.png
[ 104.7s] shot 13-settings-api-guardrails.png
[ 105.2s] shot 14-settings-orchestrator-overlap-recursion.png
[ 105.3s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[ 107.3s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 232.1s] run 1881a326-dbc0-462c-8c13-869c83e68d44 → completed after 123s
[ 233.3s] run 1881a326 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 233.3s] answer: The remote polyglot agent was asked to research **tick-bounded polling** with a non-blocking timeout, but it did not return substantive findings within the ~10-
[ 233.3s] parked: true
[ 233.4s] shot 15-poll-throttle-parked-answer.png
[ 263.5s] after 30s with poll=5s but tick=60s: this run's task parked, parked (effective cadence is max(tick, interval))
[ 266.3s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 266.7s] settings ← {"ambient_tick_interval_s":15}
[ 387.2s] tick lowered to 15s → delivered within 2 minutes: false
[ 388.4s] shot 17-poll-interval-lowered-task-delivered.png
[ 391.7s] shot 18-poll-inbox-delivery.png
[ 391.8s] settings ← {"overlap_threshold_percent":10}
[ 394.5s] shot 19-overlap-near-duplicate-form.png
[ 400.3s] overlap judge flagged the save — dialog shown
[ 400.6s] shot 20-overlap-dialog-at-threshold-10.png
[ 401.2s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 401.6s] settings ← {"overlap_threshold_percent":70}
[ 403.3s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 403.5s] shot 21-guardrails-burst-5.png
[ 403.5s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 405.2s] shot 23-ambient-toast-before.png
[ 405.3s] tier-0 delivery seeded server-side: 739b5424-127d-4587-97eb-8134146f0bbb
[ 445.4s] no toast within 40s (a tier-0 delivery needs the interrupt tick + SSE)
[ 445.5s] shot 24-ambient-toast-visible.png
[ 445.5s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":60,"a2a_task_timeout_s":120,"ambient_quiet_hours":["21:48","22:18"]}
[ 445.5s] # end — 2026-09-10T20:14:40.462Z
```
