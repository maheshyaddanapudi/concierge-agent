```
[   0.0s] # 35-schema-drift — 2026-09-11T01:26:57.770Z
[   0.1s] settings ← {"orchestrator_mode":"graph","mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[   3.7s] demo-stub.echo before: schema v7 hash=700480b4dcb5 params=text changed_at=null
[   6.3s] shot 00-tools-echo-before.png
[   7.3s] shot 01-drawer-schema-v7.png
[   9.8s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[  20.9s] run 8495064d-c56a-40c5-9658-cc8f868bb88e → completed after 9s
[  22.1s] run 8495064d → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[  22.1s] answer: The demo-stub echo tool returned: `drift`.
[  22.1s] tool_call step before the change: entity_version=7 entity_hash=700480b4dcb5
[  22.1s] run snapshot s1 payload: schema_version=7 schema_hash=700480b4dcb5 input_schema params=text
[  25.1s] shot 02-trace-tool-call-schema-v7.png
[  27.6s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[  44.8s] run 95f7cd65-c2b5-4bc3-95be-534b570457b4 → completed after 15s
[  46.0s] run 95f7cd65 → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[  46.0s] answer: `schema mutated: echo now takes message`
[  46.0s] mutate attempt 1: routed to demo-stub.mutate_schema
[  47.5s] demo-stub.echo after: schema v8 hash=7f9de09d4d3b params=message status=active ingest_state=present changed_at=2026-09-11T01:27:33.183346Z
[  49.9s] shot 03-tools-badge-schema-changed.png
[  50.9s] shot 04-drawer-banner-v8.png
[  52.2s] acknowledged: changed_at=null version=8 (the version stays)
[  52.3s] shot 05-drawer-acknowledged.png
[  54.5s] shot 06-settings-schema-change-policy-warn.png
[  55.4s] mcp_schema_change_policy via API: quarantine
[  55.6s] shot 07-settings-policy-quarantine.png
[  56.5s] overlap_judge_model via API: openrouter:z-ai/glm-5.3
[  56.7s] shot 08-settings-overlap-judge-model.png
[  60.1s] check-overlap of a copy of 'file-ops' under the judge role (openrouter:z-ai/glm-5.3): {"overlap":true,"threshold":70,"overlap_percent":95,"match_type":"skill","match_id":"19092e43-1b77-45f0-b688-aaf1fb13bf8d","match_name":"file-ops","reasoning":"The draft ('file-ops copy') has a verbatim-identical descrip
[  62.1s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[  82.6s] run 10575d56-90f9-4c34-9014-6336787968ef → completed after 18s
[  83.8s] run 10575d56 → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[  83.8s] answer: schema mutated: echo now takes text
[  83.8s] mutate attempt 1: routed to demo-stub.mutate_schema
[  85.3s] quarantined: schema v9 status=inactive ingest_state=changed params=text
[  87.4s] after a re-ingest: status=inactive ingest_state=changed (a re-ingest never puts it back — only the acknowledgement does)
[  89.8s] shot 09-tools-quarantined.png
[  90.8s] shot 10-drawer-quarantined.png
[  92.0s] re-enabled: status=active ingest_state=present version=9 changed_at=null
[  92.1s] shot 11-drawer-re-enabled.png
[  94.6s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[ 107.8s] run 4e6f9718-531c-4f89-a066-dd3a6a899ea8 → completed after 11s
[ 109.0s] run 4e6f9718 → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[ 109.0s] answer: The echo completed successfully: **drift**.
[ 109.0s] tool_call step after the changes: entity_version=9 entity_hash=700480b4dcb5
[ 111.9s] shot 12-trace-tool-call-schema-v9.png
[ 112.4s] settings ← {"mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[ 112.4s] restored: policy warn, judge model default, mutate_schema unexposed
[ 112.4s] # end — 2026-09-11T01:28:50.140Z
```
