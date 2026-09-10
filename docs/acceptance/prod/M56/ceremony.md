# v1.0.0 — the §14 acceptance script on a fresh `docker compose up`

Steps 1–11 of spec §14 driven through the shipped API against the v1.0.0 images on empty volumes (`docker compose down -v` first), `default_model=openrouter:qwen/qwen3.8-max`, the admin UI screenshotted after each step (`01-…png` … `11-…png`). The transcript is verbatim; the addendum below re-runs two steps whose first pass was truthful but did not exercise the intended path (see the README).

```
# v1.0.0 acceptance ceremony — spec §14 steps 1–11 — 2026-09-10T01:23:34Z
$ fresh slate: docker compose down -v; docker compose up -d (release images)
 Network concierge-agent_default Removed 
 Container concierge-agent-frontend-1 Starting 
 Container concierge-agent-frontend-1 Started 
backend /ready 200 after 1s on :8007
concierge-agent-frontend:latest 023fc2138686
concierge-agent-backend:latest e82ebfaba139
default_model at first boot: anthropic:claude-sonnet-4-6
PATCH /settings → openrouter:qwen/qwen3.8-max graph
$ step 1 — the seed: 2 MCP servers, static tools, 2 skills, research-concierge, native tools
mcp servers: [('fetch', 'inactive', 0), ('filesystem', 'inactive', 0)]
tools: 10 {('native', 'dynamic'): 10}
skills: [('file-ops', 'native'), ('memory-keeper', 'native'), ('web-research', 'native'), ('workspace-auditor', 'native'), ('workspace-curator', 'native')]
sub agents: [('research-concierge', 'custom'), ('workspace-reporter', 'custom'), ('workspace-warden', 'native')]
shot 01-seed-tools
$ step 2 — register a new stdio MCP server → its tools appear with {server}.{tool} keys
server: demo-stub active tools 4
new tool keys: ['demo-stub.add', 'demo-stub.die', 'demo-stub.echo', 'demo-stub.mutate_toolset']
shot 02-mcp-registered
$ step 3 — custom skill summarize-site from those tools + persona; badges on Tools and Skills
skill: summarize-site custom tools ['demo-stub.echo', 'demo-stub.add']
tool badge (used by skills): []
shot 03-skill-created
$ step 4 — toggle direct_exposure on one tool; the next chat's trace shows a rung-1 route step
PATCH → demo-stub.echo direct_exposure True
run 9eeb9675-d81d-488e-b40b-b63991e9086a → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('tool_call', '', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 04-direct-exposure-run
$ step 5 — sub agent with a branch, an error edge and an HITL node; a validation error is rejected inline, then fixed
{"detail":"edge references unknown node 'ghost'"}
→ HTTP 422
sub agent: site-reporter custom nodes ['sum:skill', 'approve:hitl', 'recover:skill'] edges 6
shot 05-sub-agent
$ step 6 — multi-turn chat: message 1 invokes the new sub agent (HITL approved mid-run); message 2 follows up on message 1's result
run bcaf8088-7f72-41a9-8b8e-9afa3625dced paused at the HITL gate after 17s
shot 06a-hitl-card
hitl → {'status': 'resuming', 'decision': 'approve'}
run bcaf8088-7f72-41a9-8b8e-9afa3625dced → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: The summary was approved, and it reads:
“The demo site’s key claim is that 21 and 21 make the answer — which is 42.”
run 14e76bcc-1ee4-4c64-8855-4e8b0433f112 → completed
follow-up answer: 42
shot 06b-multi-turn
$ step 7 — something no capability covers → the planner reports no confident match; the trace shows the fallback route rung
run 23f08cce-aed9-4bf1-b985-d41a94e26dbb → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', '', 'completed', ''), ('tool_call', 'filesystem_list_allowed_directories', 'completed', ''), ('tool_call', 'memory_recall', 'completed', ''), ('tool_call', 'filesystem_list_directory_with_sizes', 'completed', ''), ('tool_call', 'filesystem_search_files', 'completed', ''), ('tool_call', 'filesystem_directory_tree', 'completed', ''), ('tool_call', 'filesystem_search_files', 'completed', ''), ('tool_call', 'filesystem_search_files', 'completed', ''), ('aggregate', '', 'completed', '')]
answer: I couldn’t complete the reconciliation or list mismatches.
Concrete results:
- The requested invoice-reconciliation function is not availab
$ step 8 — kill the new MCP server process → invoke again → error edge; the server shows error; reconnect from the API
run 32e05925-f273-4454-ba4d-c152d8d0f403 → completed
[('plan', '', 'completed', ''), ('route', '', 'completed', ''), ('skill', 's1', 'failed', ''), ('tool_call', 'demo-stub_add', 'failed', ''), ('tool_call', 'demo-stub_echo', 'failed', ''), ('tool_call', 'demo-stub_add', 'failed', ''), ('tool_call', 'demo-stub_echo', 'failed', ''), ('aggregate', '', 'completed', '')]
server after the kill (the manager respawns a stdio server on next use — M36 noted the same): error | health ping failed
(the visible error state: point the server at a binary that does not exist, reconnect, then restore — the same lifecycle the UI drives)
reconnect with a broken command → error | FileNotFoundError: [Errno 2] No such file or directory
reconnect restored → active tools 4
shot 08-server-reconnected
$ step 9 — Runs page: full trace with nested steps, tokens, route reasons; cancel a running run; retry a failed one
trace: 10 steps; tokens 3438 → 865 ; nested: 6
cancel → {'status': 'cancelled'}
cancelled|run cancelled
(a run that fails truthfully: run_wall_clock_s=30 — the M51 ceiling — under a long essay)
run_wall_clock_s → 30
run under the 30 s wall clock 6533659d-14b0-4765-b01d-54bf4e2367a6 → failed
failed|exceeded the run wall clock (30s, run_wall_clock_s) — terminated
retry → run 7e446bfc-ee06-4cf1-89d5-f94b974e4639 → timeout
shot 09-runs
$ step 10 — Settings: change the planner model → the next run's trace labels show it
planner_model → openrouter:qwen/qwen3.8-max
run 951a0cd6-2c22-42fd-804b-e0904b4f35ba → completed
step models: [('plan', 'openrouter:qwen/qwen3.8-max'), ('aggregate', 'openrouter:qwen/qwen3.8-max')]
shot 10-settings
$ step 11 — orchestrator_mode=agentic: repeat step 6's first message; todo events stream, the sub agent is a dispatch tool, the HITL card still gates
orchestrator_mode → agentic
paused at the HITL gate after 17s
run d1f9c8d8-c316-4aa8-b49e-177fb797847b → completed
     18 event: activity       1 event: dispatch_end       1 event: dispatch_start       1 event: done       2 event: hitl_request       1 event: route       4 event: run_status       1 event: token 
[('route', '', 'completed', ''), ('skill', 'agentic:site-reporter', 'completed', ''), ('tool_call', 'demo-stub_add', 'completed', ''), ('tool_call', 'demo-stub_echo', 'completed', ''), ('route', 'route:sum', 'completed', 'router model selected condition'), ('skill', 'sum', 'completed', ''), ('hitl', 'approve', 'completed', ''), ('route', 'route:approve', 'completed', ''), ('aggregate', '', 'completed', '')]
shot 11-agentic
# end — 2026-09-10T01:32:53Z
```
