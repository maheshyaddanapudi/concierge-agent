# acceptance ceremony — spec §14 steps 1–11 — 2026-09-11T22:24:49Z

$ fresh slate: docker compose down -v; docker compose up -d
 Network concierge-agent_default Removed 
 Container concierge-agent-frontend-1 Starting 
 Container concierge-agent-frontend-1 Started 
backend /ready 200 after 1s at http://localhost:8000
concierge-agent-backend:latest 28f57ea17cd6
concierge-agent-frontend:latest 89fbe59b7888
default_model at first boot: anthropic:claude-sonnet-4-6
PATCH /settings → openrouter:qwen/qwen3.8-max graph

$ step 1 — the seed: MCP servers, static tools, native skills, research-concierge
mcp servers: [('fetch', 'active', 1), ('filesystem', 'active', 14)]
tools: 25 {('native', 'static'): 10, ('mcp', 'static'): 15}
skills: [('file-ops', 'native'), ('memory-keeper', 'native'), ('web-research', 'native'), ('workspace-auditor', 'native'), ('workspace-curator', 'native')]
sub agents: [('research-concierge', 'custom'), ('workspace-reporter', 'custom'), ('workspace-warden', 'native')]
shot 01-seed-tools.png

$ step 2 — register a new stdio MCP server → its tools appear with {server}.{tool} keys
server: demo-stub active tools 5
new tool keys: ['demo-stub.add', 'demo-stub.die', 'demo-stub.echo', 'demo-stub.mutate_schema', 'demo-stub.mutate_toolset']
shot 02-mcp-registered.png

$ step 3 — custom skill summarize-site from those tools + persona; badges on Tools and Skills
skill: summarize-site custom tools ['demo-stub.echo', 'demo-stub.add']
tool badge (used by skills): []
shot 03-skill-created.png

$ step 4 — toggle direct_exposure on one tool; the next chat's trace shows a rung-1 route step
PATCH → demo-stub.echo direct_exposure True
run a4c048af-c1dc-430a-ac6a-ac0912f8cda9 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 04-direct-exposure-run.png

$ step 5 — sub agent with a branch, an error edge and an HITL node; a validation error is rejected inline, then fixed
{"detail":"edge references unknown node 'ghost'"}
→ HTTP 422
sub agent: site-reporter custom nodes ['sum:skill', 'approve:hitl', 'recover:skill'] edges 6
shot 05-sub-agent.png

$ step 6 — multi-turn chat: message 1 invokes the new sub agent (HITL approved mid-run); message 2 follows up on message 1's result
run 25f5cd4a-2e69-4665-bb39-2b659b5c97a6 paused at the HITL gate after 22s
shot 06a-hitl-card.png
hitl → {'status': 'resuming', 'decision': 'approve'}
run 25f5cd4a-2e69-4665-bb39-2b659b5c97a6 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: The summary is: **“The demo site says 21 and 21 make 42.”**

It was **not published**, because no publishing tool was available, so no published link exists.
run 53827a4c-2b1f-4906-9e90-e86d4274faae → completed
follow-up answer: 42
shot 06b-multi-turn.png

$ step 7 — something no capability covers → the planner reports no confident match; the trace shows the fallback route rung
run 81ea27e4-53ab-4157-b94e-0a64a5bddb55 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', '', 'completed', ''), ('tool_call', 'filesystem_search_files', 'completed', ''), ('tool_call', 'filesystem_list_allowed_directories', 'completed', ''), ('tool_call', 'filesystem_directory_tree', 'completed', ''), ('tool_call', 'filesystem_search_files', 'completed', ''), ('tool_call', 'memory_recall', 'completed', ''), ('tool_call', 'filesystem_list_directory_with_sizes', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: I couldn’t complete the reconciliation or produce a mismatch list.

Two concrete blockers were found:

1. **The requested invoice-reconcilia

$ step 8 — kill the new MCP server process → invoke again → the server shows error; reconnect from the API
run e2bdeb3e-c868-43d9-a2e6-144f58463556 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
server after the kill (a stdio server respawns on next use): active | 
(the visible error state: point the server at a binary that does not exist, reconnect, then restore — the same lifecycle the UI drives)
reconnect with a broken command → error | FileNotFoundError: [Errno 2] No such file or directory
reconnect restored → active tools 5
shot 08-server-reconnected.png

$ step 9 — Runs page: full trace with nested steps, tokens, route reasons; cancel a running run; retry a failed one
trace: 10 steps; tokens 3529 → 926 ; nested: 6
cancel → {'status': 'cancelled'}
cancelled run cancelled
(a run that fails truthfully: run_wall_clock_s=30 — the admission ceiling — under a long essay)
run_wall_clock_s → 30
run under the 30 s wall clock 78dd3ae0-dc1e-46b3-aac1-1736a174d16f → failed
failed exceeded the run wall clock (30s, run_wall_clock_s) — terminated
retry → run acfc2052-1405-4fc0-865b-362adc22d578 → completed
shot 09-runs.png

$ step 10 — Settings: change the planner model → the next run's trace labels show it
planner_model → openrouter:qwen/qwen3.8-max
run 09798408-1958-4865-8ec5-b747a57088c5 → completed
step models: [('plan', 'openrouter:qwen/qwen3.8-max')]
shot 10-settings.png

$ step 11 — orchestrator_mode=agentic: repeat step 6's first message; the sub agent is a dispatch tool, the HITL card still gates
orchestrator_mode → agentic
run ff0569f3-16cf-421b-81cf-f9a0c34b1202 → completed
     20 event: activity
       1 event: dispatch_end
       1 event: dispatch_start
       1 event: done
       2 event: hitl_request
       1 event: route
       4 event: run_status
       1 event: token
 
[('route', '', 'completed', ''), ('skill', 'agentic:site-reporter', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 11-agentic.png
# end — 2026-09-11T22:31:17Z

## alembic current on the fresh volume
w2k3l4m5n6o7 (head)
w2k3l4m5n6o7
30|30
human|6
