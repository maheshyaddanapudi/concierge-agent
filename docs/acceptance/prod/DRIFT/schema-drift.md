# schema drift — 2026-09-11T01:19:54Z — model openrouter:qwen/qwen3.8-max

$ settings ← mcp_schema_change_policy=warn; the demo-stub server reconnected (the image's stub carries mutate_schema)

$ demo-stub.echo before: {"id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "status": "active", "ingest_state": "present", "schema_version": 3, "schema_changed_at": null, "schema_hash": "700480b4dcb5", "params": ["text"]}

$ a run that calls echo (v3): the tool_call step and the run snapshot pin the version
run d9061067-a238-48a7-b554-577c8f619a7c → completed
  tool_call demo-stub_echo: entity_version=3 entity_hash=700480b4dcb5
  snapshot s1: rung=direct_tool schema_version=3 schema_hash=700480b4dcb5 params=['text']

$ the server renames the parameter: a run calls demo-stub.mutate_schema
run cb1ab0b5-52fc-4c3e-9988-348457bb8e3b → completed
  attempt 1 routed to: demo-stub.mutate_schema
schema_version 3 → 4 after 1s

$ demo-stub.echo after (warn): {"id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "status": "active", "ingest_state": "present", "schema_version": 4, "schema_changed_at": "2026-09-11T01:20:26.487698Z", "schema_hash": "7f9de09d4d3b", "params": ["message"]}

$ the ingest log line
{"server_id": "387e1e2c-dc23-4a7b-9c35-e490a96c656b", "tool_count": 5, "schema_changed": [], "event": "mcp_tools_ingested", "level": "info", "timestamp": "2026-09-11T01:19:55.150750Z"}
{"tool_id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "tool_key": "demo-stub.echo", "kind": "mcp", "schema_version": 4, "previous_hash": "700480b4dcb5", "schema_hash": "7f9de09d4d3b", "policy": "warn", "quarantined": false, "event": "tool_schema_changed", "level
{"server_id": "387e1e2c-dc23-4a7b-9c35-e490a96c656b", "tool_count": 5, "schema_changed": ["demo-stub.echo"], "event": "mcp_tools_ingested", "level": "info", "timestamp": "2026-09-11T01:20:26.497676Z"}

$ the metric
concierge_tool_schema_changes_total{kind="mcp",policy="warn"} 2.0

$ acknowledged through the API (the flag clears, the version stays)
{'status': 'active', 'ingest_state': 'present', 'schema_version': 4, 'schema_changed_at': None}

$ settings ← mcp_schema_change_policy=quarantine; the same change again (the stub flips the parameter back)
run 31b24aac-f27f-404d-855a-d0b87cca128b → completed
  attempt 1 routed to: demo-stub.mutate_schema
schema_version 4 → 5 after 1s

$ demo-stub.echo after (quarantine): {"id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "status": "inactive", "ingest_state": "changed", "schema_version": 5, "schema_changed_at": "2026-09-11T01:20:50.020354Z", "schema_hash": "700480b4dcb5", "params": ["text"]}

$ a re-ingest does not put it back
{"id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "status": "inactive", "ingest_state": "changed", "schema_version": 5, "schema_changed_at": "2026-09-11T01:20:50.020354Z", "schema_hash": "700480b4dcb5", "params": ["text"]}

$ an ask that needs echo while it is quarantined
run 36b6b4b9-bb43-4a7a-9369-368783bcb580 → completed
  status: completed | routes: ['fallback', 'fallback'] | tool calls: []

$ acknowledged: back in service
{'status': 'active', 'ingest_state': 'present', 'schema_version': 5, 'schema_changed_at': None}

$ the metric now
concierge_tool_schema_changes_total{kind="mcp",policy="warn"} 2.0
concierge_tool_schema_changes_total{kind="mcp",policy="quarantine"} 1.0

$ restored: policy warn, mutate_schema unexposed

$ verdict: {"id": "c3c6eea6-fe9d-48d7-b93e-cf1cbd3e5641", "status": "active", "ingest_state": "present", "schema_version": 5, "schema_changed_at": null, "schema_hash": "700480b4dcb5", "params": ["text"]}
