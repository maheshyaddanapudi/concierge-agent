# ceremony addendum — 2026-09-11T22:31:18Z

$ step 8 (second pass) — the sub agent invoked DIRECTLY (spec §7.5) so its DAG runs: a tool-less 'apology-note' skill on the recover branch, the stub broken, the error edge taken, the run completes via recover
PATCH sub agent → nodes ['sum', 'approve', 'recover']
server: error | FileNotFoundError: [Errno 2] No such file or directory
direct invocation run a2712d79-b7e5-4acf-b202-8ea1fbda30dc → completed
[('route', None, 'completed'), ('skill', 'direct', 'completed'), ('tool_call', 'demo-stub_add', 'failed'), ('tool_call', 'demo-stub_echo', 'failed'), ('skill', 'recover', 'completed'), ('route', 'route:recover', 'completed'), ('route', 'route:sum', 'completed'), ('skill', 'sum', 'failed')]
answer: The summary could not be produced because the prior “sum” step failed: the MCP server was not connected.
server restored: active tools 5

$ step 11 (addendum) — agentic mode with a multi-step ask: the todo list streams as plan events
run 3bae56ef-b390-443a-b959-849bd0f60b4f → completed
plan event seq 2 mode agentic todos [('Locate a demo-stub add capability (not curren', 'in_progress'), ('Use demo-stub add to compute 40 + 2', 'pending'), ('Use demo-stub echo to echo the addition resul', 'pending'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 9 mode agentic todos [('Locate a demo-stub add capability (not curren', 'completed'), ('Use demo-stub add to compute 40 + 2', 'completed'), ('Use demo-stub echo to echo the addition resul', 'in_progress'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 11 mode agentic todos [('Locate a demo-stub add capability (not curren', 'completed'), ('Use demo-stub add to compute 40 + 2', 'completed'), ('Use demo-stub echo to echo the addition resul', 'completed'), ('Report both the addition result and the echo ', 'completed')]
# end — 2026-09-11T22:32:01Z
