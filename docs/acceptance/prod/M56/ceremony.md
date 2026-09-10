# acceptance ceremony — spec §14 steps 1–11 — 2026-09-10T22:21:41Z

$ fresh slate: docker compose down -v; docker compose up -d
 Network concierge-agent_default Removed 
 Container concierge-agent-frontend-1 Starting 
 Container concierge-agent-frontend-1 Started 
backend /ready 200 after 1s at http://localhost:8000
concierge-agent-frontend:latest d6c0a08281f8
concierge-agent-backend:latest ba6942fd566d
default_model at first boot: anthropic:claude-sonnet-4-6
PATCH /settings → openrouter:qwen/qwen3.8-max graph

$ step 1 — the seed: MCP servers, static tools, native skills, research-concierge
mcp servers: [('fetch', 'active', 1), ('filesystem', 'active', 14)]
tools: 25 {('native', 'static'): 10, ('mcp', 'static'): 15}
skills: [('file-ops', 'native'), ('memory-keeper', 'native'), ('web-research', 'native'), ('workspace-auditor', 'native'), ('workspace-curator', 'native')]
sub agents: [('research-concierge', 'custom'), ('workspace-reporter', 'custom'), ('workspace-warden', 'native')]
shot 01-seed-tools.png

$ step 2 — register a new stdio MCP server → its tools appear with {server}.{tool} keys
server: demo-stub active tools 4
new tool keys: ['demo-stub.add', 'demo-stub.die', 'demo-stub.echo', 'demo-stub.mutate_toolset']
shot 02-mcp-registered.png

$ step 3 — custom skill summarize-site from those tools + persona; badges on Tools and Skills
skill: summarize-site custom tools ['demo-stub.echo', 'demo-stub.add']
tool badge (used by skills): []
shot 03-skill-created.png

$ step 4 — toggle direct_exposure on one tool; the next chat's trace shows a rung-1 route step
PATCH → demo-stub.echo direct_exposure True
run 93ae84c1-c936-401c-8ac8-65cf10b0fbb6 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('tool_call', '', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 04-direct-exposure-run.png

$ step 5 — sub agent with a branch, an error edge and an HITL node; a validation error is rejected inline, then fixed
{"detail":"edge references unknown node 'ghost'"}
→ HTTP 422
sub agent: site-reporter custom nodes ['sum:skill', 'approve:hitl', 'recover:skill'] edges 6
shot 05-sub-agent.png

$ step 6 — multi-turn chat: message 1 invokes the new sub agent (HITL approved mid-run); message 2 follows up on message 1's result
run a1a9eef3-9561-46ae-8695-4cffdbe32f8c paused at the HITL gate after 18s
shot 06a-hitl-card.png
hitl → {'status': 'resuming', 'decision': 'approve'}
run a1a9eef3-9561-46ae-8695-4cffdbe32f8c → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: The summary is: **21 + 21 = 42 makes the answer**.

It was approved, but publication could not be completed because no publish tool was available.
run 9304c414-8d6c-4591-b642-93f87b799085 → completed
follow-up answer: 42
shot 06b-multi-turn.png

$ step 7 — something no capability covers → the planner reports no confident match; the trace shows the fallback route rung
run 744246dc-f43e-495f-a40e-54dec236e5b2 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', '', 'completed', ''), ('tool_call', 'filesystem_list_allowed_directories', 'completed', ''), ('tool_call', 'filesystem_directory_tree', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: I couldn’t complete the reconciliation or list mismatches.

Concrete result from the check:

- The workspace is empty — there are no supplie

$ step 8 — kill the new MCP server process → invoke again → the server shows error; reconnect from the API
run 43835985-11c4-4a1b-a7e0-35a2760e27d9 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
server after the kill (a stdio server respawns on next use): active | 
(the visible error state: point the server at a binary that does not exist, reconnect, then restore — the same lifecycle the UI drives)
reconnect with a broken command → error | FileNotFoundError: [Errno 2] No such file or directory
reconnect restored → active tools 4
shot 08-server-reconnected.png

$ step 9 — Runs page: full trace with nested steps, tokens, route reasons; cancel a running run; retry a failed one
trace: 10 steps; tokens 3446 → 911 ; nested: 6
cancel → {'status': 'cancelled'}
cancelled run cancelled
(a run that fails truthfully: run_wall_clock_s=30 — the admission ceiling — under a long essay)
run_wall_clock_s → 30
run under the 30 s wall clock 66ba327e-27aa-4fdf-ba3b-74f81a6d6d9f → failed
failed exceeded the run wall clock (30s, run_wall_clock_s) — terminated
retry → run 0b919354-bca2-4648-b0d4-b8b841a71fc8 → timeout
shot 09-runs.png

$ step 10 — Settings: change the planner model → the next run's trace labels show it
planner_model → openrouter:qwen/qwen3.8-max
run 7b70d58e-3f9e-42f2-becb-e7dd9f9e9135 → completed
step models: [('plan', 'openrouter:qwen/qwen3.8-max'), ('aggregate', 'openrouter:qwen/qwen3.8-max')]
shot 10-settings.png

$ step 11 — orchestrator_mode=agentic: repeat step 6's first message; the sub agent is a dispatch tool, the HITL card still gates
orchestrator_mode → agentic
run 89910aa2-c151-49f3-a5a6-86177f329898 → completed
     18 event: activity       1 event: dispatch_end       1 event: dispatch_start       1 event: done       2 event: hitl_request       1 event: route       4 event: run_status       1 event: token 
[('route', '', 'completed', ''), ('skill', 'agentic:site-reporter', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 11-agentic.png
# end — 2026-09-10T22:31:09Z
