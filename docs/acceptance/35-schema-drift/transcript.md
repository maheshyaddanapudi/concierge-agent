```
[   0.0s] # 35-schema-drift — 2026-09-11T21:26:04.198Z
[   0.0s] settings ← {"orchestrator_mode":"graph","mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[   3.7s] demo-stub.echo before: schema v9 hash=700480b4dcb5 params=text changed_at=null
[   6.2s] shot 00-tools-echo-before.png
[   7.2s] shot 01-drawer-schema-v9.png
[   9.7s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[  30.0s] run 2d121ab1-34f1-4510-82bc-c83544a348bf → completed after 18s
[  31.2s] run 2d121ab1 → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[  31.2s] answer: The echo result was: **drift**
[  31.2s] tool_call step before the change: entity_version=9 entity_hash=700480b4dcb5
[  31.2s] run snapshot s1 payload: schema_version=9 schema_hash=700480b4dcb5 input_schema params=text
[  34.1s] shot 02-trace-tool-call-schema-v9.png
[  36.7s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[  53.9s] run 642e5b56-29b6-43db-ad23-34a994e80a92 → completed after 15s
[  55.1s] run 642e5b56 → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[  55.1s] answer: schema mutated: echo now takes message
[  55.1s] mutate attempt 1: routed to demo-stub.mutate_schema
[  56.6s] demo-stub.echo after: schema v10 hash=7f9de09d4d3b params=message status=active ingest_state=present changed_at=2026-09-11T21:26:48.995840Z
[  59.0s] shot 03-tools-badge-schema-changed.png
[  60.0s] shot 04-drawer-banner-v10.png
[  61.3s] acknowledged: changed_at=null version=10 (the version stays)
[  61.4s] shot 05-drawer-acknowledged.png
[  63.7s] shot 06-settings-schema-change-policy-warn.png
[  64.7s] mcp_schema_change_policy via API: quarantine
[  64.8s] shot 07-settings-policy-quarantine.png
[  65.8s] overlap_judge_model via API: openrouter:z-ai/glm-5.3
[  65.9s] shot 08-settings-overlap-judge-model.png
[  73.1s] check-overlap of a copy of 'file-ops' under the judge role (openrouter:z-ai/glm-5.3): {"overlap":true,"threshold":1,"overlap_percent":97,"match_type":"skill","match_id":"19092e43-1b77-45f0-b688-aaf1fb13bf8d","match_name":"file-ops","reasoning":"The draft is named 'file-ops copy' and carries a description 
[  75.2s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[  90.4s] run 7fff35ed-0507-4d2d-ba3b-62989ae3991f → completed after 13s
[  91.6s] run 7fff35ed → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[  91.6s] answer: schema mutated: echo now takes text
[  91.6s] mutate attempt 1: routed to demo-stub.mutate_schema
[  93.1s] quarantined: schema v11 status=inactive ingest_state=changed params=text
[  95.1s] after a re-ingest: status=inactive ingest_state=changed (a re-ingest never puts it back — only the acknowledgement does)
[  97.6s] shot 09-tools-quarantined.png
[  98.6s] shot 10-drawer-quarantined.png
[  99.8s] re-enabled: status=active ingest_state=present version=11 changed_at=null
[ 100.0s] shot 11-drawer-re-enabled.png
[ 102.5s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[ 122.8s] run 25c587be-7501-49a6-9728-5db72a6d94a7 → completed after 18s
[ 124.0s] run 25c587be → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[ 124.0s] answer: The echo returned: **drift**.
[ 124.0s] tool_call step after the changes: entity_version=11 entity_hash=700480b4dcb5
[ 126.9s] shot 12-trace-tool-call-schema-v11.png
[ 127.4s] settings ← {"mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[ 127.4s] restored: policy warn, judge model default, mutate_schema unexposed
[ 127.4s] # end — 2026-09-11T21:28:11.595Z
```
