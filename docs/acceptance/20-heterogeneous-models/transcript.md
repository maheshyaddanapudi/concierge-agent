```
[   0.0s] # 20-heterogeneous-models — 2026-09-10T18:22:41.271Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model":"openrouter:qwen/qwen3.8-max","default_model_params":{"effort":"high"},"planner_model":null,"formatter_model":null}
[   3.4s] settings ← {"planner_model_params":{"effort":"high"},"formatter_model_params":{"effort":"medium"}}
[   4.9s] roles: default=openrouter:qwen/qwen3.8-max@high planner=openrouter:qwen/qwen3.6-plus@high aggregator=(default) formatter=openrouter:qwen/qwen3.6-plus@medium
[   5.6s] shot 00-role-mix-settings.png
[   7.7s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  36.5s] shot 01-gate.png
[  36.6s] gate approved from the chat card
[  55.5s] run a3156bdc-1e4d-4a28-af45-b76a4d55fb63 still running after 45s (wait timed out)
[  59.0s] run a3156bdc-1e4d-4a28-af45-b76a4d55fb63 → completed after 22s
[  60.2s] run a3156bdc → completed; steps: plan::completed route::completed skill:s1:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed aggregate::completed
[  60.2s] answer: Published summary: “The demo site's 21 + 21 gives an answer of 42.”
[  60.4s] shot 02-answer-role-mix.png
[  60.4s] models per step: plan=openrouter:qwen/qwen3.6-plus | route=- | skill:s1=- | tool_call:sitefiles_add=- | tool_call:sitefiles_echo=- | route:route:work=- | skill:work=openrouter:qwen/qwen3.8-max | tool_call:sitefiles_echo=- | tool_call:sitefiles_add=- | hitl:approve=- | skill:finish=openrouter:qwen/qwen3.8-max | route:route:approve=- | route:route:finish=- | aggregate=openrouter:qwen/qwen3.8-max
[  60.4s] plan step model=openrouter:qwen/qwen3.6-plus formatter step model=(no formatter step recorded)
[  64.0s] shot 03-trace-models-per-step.png
[  64.6s] settings ← {"planner_model":null,"planner_model_params":null,"formatter_model":null,"formatter_model_params":null,"default_model_params":null}
[  64.6s] roles restored to the default model
[  64.6s] # end — 2026-09-10T18:23:45.823Z
```
