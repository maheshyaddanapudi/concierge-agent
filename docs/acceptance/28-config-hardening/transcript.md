```
[   0.0s] # 28-config-hardening — 2026-09-11T21:34:09.404Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"ambient_enabled":true,"a2a_enabled":true}
[   2.6s] shot 00-conv-a-pinned.png
[   2.7s] UI send: Summarize this: 8 and 9 make seventeen; publish the summary.
[  14.8s] run 1664e052-46fd-411c-a1e0-ef8584f16a1a → failed after 10s
[  14.8s] run 1664e052-46fd-411c-a1e0-ef8584f16a1a → failed after 0s
[  16.0s] run 1664e052 → failed; steps: route::completed skill:direct:failed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed
[  16.0s] answer: 
[  16.0s] conversation A run: target=site-analyst (direct) status=failed
[  16.2s] shot 01-conv-a-direct-run.png
[  17.1s] conversation B picker:  (empty = Orchestrator (auto))
[  17.2s] shot 02-conv-b-picker-auto.png
[  17.3s] UI send: Use the sitefiles add tool to add 3 and 4. Number only.
[  38.6s] run 2f294b79-8ede-47b1-8e66-5174cdcb67c2 → completed after 19s
[  38.6s] run 2f294b79-8ede-47b1-8e66-5174cdcb67c2 → completed after 0s
[  39.8s] run 2f294b79 → completed; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  39.8s] answer: 7
[  39.8s] conversation B run: target=orchestrator status=completed
[  39.9s] shot 03-conv-b-planner-run.png
[  42.0s] back in A: pin restored=true
[  42.0s] history-summary option not rendered (needs a completed run in the pinned conversation)
[  42.1s] shot 04-conv-a-pin-restored-summary-checked.png
[  44.0s] back in B: picker=auto
[  44.1s] shot 05-conv-b-still-auto.png
[  46.0s] UI send: Now summarize this too: 20 and 22 make forty-two; publish it.
[  62.9s] gate approved from the chat card
[  69.6s] run 5df55715-cb66-435f-8532-b45e1db3c9d6 → completed after 22s
[  70.0s] run 5df55715-cb66-435f-8532-b45e1db3c9d6 → completed after 7s
[  71.2s] run 5df55715 → completed; steps: route::completed skill:direct:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed
[  71.2s] answer: approved 20 + 22 = 42 (no publish tool available, so it's reported here only). 20 + 22 = 42.
[  71.2s] conversation A second run: target=direct include_history_summary=false
[  71.4s] shot 06-conv-a-second-direct-plus-ctx.png
[  73.2s] shot 09-settings-ambient-knobs.png
[  74.2s] tick read-back: settings.ambient_tick_interval_s=45; field shows 45
[  74.4s] shot 10-settings-tick-45-readback.png
[  75.6s] tick=5 → inline: ambient_tick_interval_s must be an integer >= 15; setting still 45
[  75.7s] shot 11-settings-422-inline.png
[  77.1s] shot 12-settings-a2a-on-knobs.png
[  77.6s] shot 13-settings-api-guardrails.png
[  78.1s] shot 14-settings-orchestrator-overlap-recursion.png
[  78.1s] settings ← {"ambient_tick_interval_s":60,"a2a_poll_interval_s":5,"a2a_task_timeout_s":10,"ambient_quiet_hours":[]}
[  80.2s] UI send: Ask the remote polyglot agent to research tick-bounded polling; do not wait if i
[ 128.9s] run dad3f6c3-dd80-4882-aabb-b7f010ee40d0 → completed after 47s
[ 130.1s] run dad3f6c3 → completed; steps: plan::completed route::completed skill::completed tool_call:polyglot-agent_research:completed aggregate::completed
[ 130.1s] answer: I asked the remote polyglot agent to research **tick-bounded polling** — including its definition, where it appears, and trade-offs versus blocking waits and un
[ 130.1s] parked: false
[ 130.2s] shot 15-poll-throttle-parked-answer.png
[ 160.2s] after 30s with poll=5s but tick=60s: this run's task completed/delivered (effective cadence is max(tick, interval))
[ 163.1s] shot 16-poll-throttle-still-parked-after-ticks.png
[ 163.5s] settings ← {"ambient_tick_interval_s":15}
[ 163.5s] tick lowered to 15s → delivered within 2 minutes: true
[ 164.7s] shot 17-poll-interval-lowered-task-delivered.png
[ 168.1s] shot 18-poll-inbox-delivery.png
[ 168.2s] settings ← {"overlap_threshold_percent":10}
[ 170.9s] shot 19-overlap-near-duplicate-form.png
[ 177.5s] overlap judge flagged the save — dialog shown
[ 177.9s] shot 20-overlap-dialog-at-threshold-10.png
[ 178.4s] near-duplicate save at threshold 10% → {"outcome":"saved","text":"","sawOverlap":true}
[ 178.8s] settings ← {"overlap_threshold_percent":1}
[ 180.5s] rate_limit_burst=5 rate_limit_per_s=1 set live (the 429 boundary is exercised under an identity in prod/m34-auth.sh)
[ 180.7s] shot 21-guardrails-burst-5.png
[ 180.7s] settings ← {"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 182.4s] shot 23-ambient-toast-before.png
[ 182.5s] tier-0 delivery seeded server-side: fdbfb131-e4bc-4da0-b232-45764ef564b7
[ 222.6s] no toast within 40s (a tier-0 delivery needs the interrupt tick + SSE)
[ 222.7s] shot 24-ambient-toast-visible.png
[ 222.7s] settings ← {"ambient_tick_interval_s":15,"a2a_poll_interval_s":60,"a2a_task_timeout_s":120,"ambient_quiet_hours":[]}
[ 225.4s] ambient off → nav Ambient links: 0
[ 225.6s] shot 07-settings-ambient-master-off.png
[ 226.6s] ambient on → nav Ambient links: 1
[ 226.8s] shot 08-settings-ambient-on-nav-live.png
[ 226.8s] note: this off/on once stalled the leader tick until a restart (report.md finding 2, fixed — prod/FIXES/ambient-toggle.md re-verifies it); nothing in this stage depends on the tick afterwards
[ 226.8s] # end — 2026-09-11T21:37:56.167Z
```
