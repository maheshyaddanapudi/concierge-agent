```
[   0.0s] # 35-schema-drift — 2026-09-11T22:52:09.412Z
[   0.1s] settings ← {"orchestrator_mode":"graph","mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[   3.8s] demo-stub.echo before: schema v3 hash=700480b4dcb5 params=text changed_at=null
[   6.4s] shot 00-tools-echo-before.png
[   7.4s] shot 01-drawer-schema-v3.png
[   9.9s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[  36.3s] run 0439a4c0-2f38-4405-8c76-932b0e841403 → completed after 24s
[  37.5s] run 0439a4c0 → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[  37.5s] answer: The requested echo returned: **drift**.
[  37.5s] tool_call step before the change: entity_version=3 entity_hash=700480b4dcb5
[  37.5s] run snapshot s1 payload: schema_version=3 schema_hash=700480b4dcb5 input_schema params=text
[  40.4s] shot 02-trace-tool-call-schema-v3.png
[  43.0s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[  62.2s] run 9b122ae5-ec36-49c6-9f74-8099730b67e3 → completed after 17s
[  63.4s] run 9b122ae5 → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[  63.4s] answer: schema mutated: echo now takes message
[  63.4s] mutate attempt 1: routed to demo-stub.mutate_schema
[  64.9s] demo-stub.echo after: schema v4 hash=7f9de09d4d3b params=message status=active ingest_state=present changed_at=2026-09-11T22:53:01.379271Z
[  67.3s] shot 03-tools-badge-schema-changed.png
[  68.3s] shot 04-drawer-banner-v4.png
[  69.6s] acknowledged: changed_at=null version=4 (the version stays)
[  69.7s] shot 05-drawer-acknowledged.png
[  71.9s] shot 06-settings-schema-change-policy-warn.png
[  72.9s] mcp_schema_change_policy via API: quarantine
[  73.0s] shot 07-settings-policy-quarantine.png
[  74.0s] overlap_judge_model via API: openrouter:z-ai/glm-5.3
[  74.1s] shot 08-settings-overlap-judge-model.png
[  82.9s] check-overlap of a copy of 'file-ops' under the judge role (openrouter:z-ai/glm-5.3): {"overlap":true,"threshold":1,"overlap_percent":97,"match_type":"skill","match_id":"7ed3d0de-3520-419c-9afe-2b8b3aa8064c","match_name":"file-ops","reasoning":"The draft ('file-ops copy') is a verbatim duplicate of the ex
[  85.0s] UI send: Call the tool named demo-stub.mutate_schema — not echo, not add — with no argume
[ 108.2s] run 9d16c7d9-5818-45cc-9089-550d7cdee211 → completed after 21s
[ 109.4s] run 9d16c7d9 → completed; steps: plan::completed route::completed tool_call:demo-stub_mutate_schema:completed aggregate::completed
[ 109.4s] answer: demo-stub.mutate_schema replied: `schema mutated: echo now takes text`
[ 109.4s] mutate attempt 1: routed to demo-stub.mutate_schema
[ 111.0s] quarantined: schema v5 status=inactive ingest_state=changed params=text
[ 113.0s] after a re-ingest: status=inactive ingest_state=changed (a re-ingest never puts it back — only the acknowledgement does)
[ 115.5s] shot 09-tools-quarantined.png
[ 116.4s] shot 10-drawer-quarantined.png
[ 117.7s] re-enabled: status=active ingest_state=present version=5 changed_at=null
[ 117.8s] shot 11-drawer-re-enabled.png
[ 120.3s] UI send: Use the demo-stub echo tool to echo the word drift, passing it as the text argum
[ 138.6s] run dae853fe-bbf0-46de-bd41-ee89b0a499c2 → completed after 16s
[ 139.8s] run dae853fe → completed; steps: plan::completed route::completed tool_call:demo-stub_echo:completed aggregate::completed
[ 139.8s] answer: The echoed result was: **drift**.
[ 139.8s] tool_call step after the changes: entity_version=5 entity_hash=700480b4dcb5
[ 142.7s] shot 12-trace-tool-call-schema-v5.png
[ 143.2s] settings ← {"mcp_schema_change_policy":"warn","overlap_judge_model":null,"overlap_judge_model_params":null}
[ 143.2s] restored: policy warn, judge model default, mutate_schema unexposed
[ 143.2s] # end — 2026-09-11T22:54:32.616Z
```
