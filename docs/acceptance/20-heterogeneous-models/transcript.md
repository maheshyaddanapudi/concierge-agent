```
[   0.0s] # 20-heterogeneous-models — 2026-09-10T03:13:55.716Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model":"openrouter:qwen/qwen3.8-max","default_model_params":{"effort":"high"},"planner_model":null,"formatter_model":null}
[   3.2s] settings ← {"planner_model_params":{"effort":"high"},"formatter_model_params":{"effort":"medium"}}
[   4.7s] roles: default=openrouter:qwen/qwen3.8-max@high planner=openrouter:qwen/qwen3.6-plus@high aggregator=(default) formatter=openrouter:qwen/qwen3.6-plus@medium
[   5.3s] shot 00-role-mix-settings.png
[   7.3s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  34.0s] shot 01-gate.png
[  34.1s] gate approved from the chat card
[  55.0s] run 64186675-8deb-4c4c-87e5-84ebb35d38e4 still running after 45s (wait timed out)
[  58.4s] run 64186675-8deb-4c4c-87e5-84ebb35d38e4 → completed after 24s
[  59.6s] run 64186675 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed aggregate::completed
[  59.6s] answer: The summary has been published: “The demo site states that 21 and 21 make the answer, which sums to 42.”
[  59.8s] shot 02-answer-role-mix.png
[  59.8s] models per step: plan=openrouter:qwen/qwen3.6-plus | route=- | skill:s1=- | tool_call:sitefiles_add=- | tool_call:sitefiles_echo=- | route:route:work=- | skill:work=openrouter:qwen/qwen3.8-max | tool_call:sitefiles_echo=- | tool_call:sitefiles_add=- | hitl:approve=- | skill:finish=openrouter:qwen/qwen3.8-max | route:route:approve=- | route:route:finish=- | aggregate=openrouter:qwen/qwen3.8-max
[  59.8s] plan step model=openrouter:qwen/qwen3.6-plus formatter step model=(no formatter step recorded)
[  63.2s] shot 03-trace-models-per-step.png
[  63.7s] settings ← {"planner_model":null,"planner_model_params":null,"formatter_model":null,"formatter_model_params":null,"default_model_params":null}
[  63.7s] roles restored to the default model
[  63.7s] # end — 2026-09-10T03:14:59.451Z
```
