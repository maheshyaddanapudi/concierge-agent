```
[   0.0s] # 31-salience-decisions — 2026-09-10T19:52:02.975Z
[   0.0s] settings ← {"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_quiet_hours":[],"ambient_salience_mode":"propose","ambient_salience_min_urgency":3,"ambient_salience_learning":"off","ambient_pursuit":"off","ambient_channels":{}}
[   2.7s] shot 00-salience-model-picker.png
[   3.7s] shot 01-extraction-model-picker.png
[   3.7s] # salience judge=openrouter:qwen/qwen3.8-max extraction=openrouter:qwen/qwen3.8-max mode=propose
[  50.2s] escalate row judged: {"tier":0,"delivered":true,"verdict":"escalate","decision":null,"applied":"false","judge_reward":null}
[  50.2s] decline row judged: {"tier":0,"delivered":true,"verdict":"drop","decision":null,"applied":"false","judge_reward":null}
[  53.2s] shot 02-escalate-proposal.png
[  53.8s] why this: A model judged this delivery after it went unseen — verdict escalate, confidence 0.93, mode proposeA 14x error-rate SLO burn with two deploys in the window, no rollback taken, and on-call never paged is an active incident with a broken noti
[  53.9s] shot 03-why-this.png
[  55.6s] after Do it: {"tier":2,"delivered":false,"verdict":"escalate","decision":"applied","applied":"true","judge_reward":"1.0"}
[  55.8s] shot 04-escalate-applied.png
[  57.4s] after Undo: {"tier":0,"delivered":true,"verdict":"escalate","decision":"undone","applied":"false","judge_reward":"-1.0"}
[  57.6s] shot 05-escalate-undone.png
[  57.8s] shot 06-low-value-proposal.png
[  59.4s] after Leave it (cold): {"tier":0,"delivered":true,"verdict":"drop","decision":"declined","applied":"false","judge_reward":"-1.0"}
[  59.6s] shot 07-declined.png
[  59.6s] the escalate row offers no second "Do it" after Undo — the second round is not available in this build (recorded as-is)
[  62.1s] precision rule toggled → false
[  62.2s] shot 11-precision-rule-toggle.png
[  62.8s] settings ← {"ambient_salience_mode":"off","ambient_salience_model":"openrouter:qwen/qwen3.8-max","memory_extraction_model":"openrouter:qwen/qwen3.8-max","ambient_tick_interval_s":15,"ambient_quiet_hours":["21:48","22:18"],"ambient_pursuit":"off"}
[  62.8s] # end — 2026-09-10T19:53:05.727Z
```
