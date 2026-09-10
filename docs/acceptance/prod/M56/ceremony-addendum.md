# ceremony addendum — 2026-09-10T22:31:09Z

$ step 8 (second pass) — the sub agent invoked DIRECTLY (spec §7.5) so its DAG runs: a tool-less 'apology-note' skill on the recover branch, the stub broken, the error edge taken, the run completes via recover
PATCH sub agent → nodes ['sum', 'approve', 'recover']
server: error | FileNotFoundError: [Errno 2] No such file or directory
direct invocation run e9dbcec4-fdc2-482b-955e-4146305e3e5d → completed
[('route', None, 'completed'), ('skill', 'direct', 'completed'), ('tool_call', 'demo-stub_add', 'failed'), ('tool_call', 'demo-stub_echo', 'failed'), ('skill', 'recover', 'completed'), ('route', 'route:recover', 'completed'), ('route', 'route:sum', 'completed'), ('skill', 'sum', 'failed')]
answer: Summary could not be produced because the prior sum step failed: the MCP server is not connected.
server restored: active tools 4

$ step 11 (addendum) — agentic mode with a multi-step ask: the todo list streams as plan events
run 28e5606d-b7ee-4a39-9802-0c997814c694 → completed
plan event seq 2 mode agentic todos [('Locate the demo-stub add capability (not in m', 'in_progress'), ('Use demo-stub add to compute 40 + 2', 'pending'), ('Use demo-stub echo to echo the computed resul', 'pending'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 6 mode agentic todos [('Locate the demo-stub add capability (not in m', 'completed'), ('Use demo-stub add to compute 40 + 2', 'in_progress'), ('Use demo-stub echo to echo the computed resul', 'pending'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 9 mode agentic todos [('Locate the demo-stub add capability (not in m', 'completed'), ('Use demo-stub add to compute 40 + 2', 'completed'), ('Use demo-stub echo to echo the computed resul', 'in_progress'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 12 mode agentic todos [('Locate the demo-stub add capability (not in m', 'completed'), ('Use demo-stub add to compute 40 + 2', 'completed'), ('Use demo-stub echo to echo the computed resul', 'completed'), ('Report both the addition result and the echo ', 'completed')]
# end — 2026-09-10T22:32:01Z
