# Ceremony addendum — steps 8 and 11 on the intended paths

Same stack, same session as `ceremony.md`. Step 8 first pass routed the chat ask to the custom skill (truthful, tools failed, run completed with an honest answer) rather than through the sub agent's DAG; here the sub agent is invoked directly (spec §7.5) with a tool-less skill on its recover branch so the error edge is the path taken. Step 11 first pass completed in agentic mode with the HITL gate but Qwen wrote no todo list for a one-line ask; here a multi-step ask makes the todo list stream as `plan` events.

```
# ceremony addendum — 2026-09-10T01:35:10Z

$ step 8 (second pass) — the sub agent invoked DIRECTLY (spec §7.5) so its DAG runs: a tool-less 'apology-note' skill on the recover branch, the stub killed, the error edge taken, the run completes via recover
PATCH sub agent → nodes ['sum', 'approve', 'recover']
server: error | FileNotFoundError: [Errno 2] No such file or directory
direct invocation run a812ea27-6673-4c78-a791-06e8a7d52596 → completed
[('route', None, 'completed'), ('skill', 'direct', 'completed'), ('tool_call', 'demo-stub_add', 'failed'), ('tool_call', 'demo-stub_echo', 'failed'), ('skill', 'recover', 'completed'), ('route', 'route:recover', 'completed'), ('route', 'route:sum', 'completed'), ('skill', 'sum', 'failed')]
answer: Summary could not be produced because the prior summarization step failed: the demo-stub_echo tool could not run because its MCP server was not connected.
server restored: active tools 4

$ step 11 (addendum) — agentic mode with a multi-step ask: the todo list streams as plan events
run 63376619-1460-42b1-b1be-d1bed22bc98e → completed
plan event seq 2 mode agentic todos [('Locate a demo-stub add capability (not curren', 'in_progress'), ('Echo the computed result using demo-stub echo', 'pending'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 9 mode agentic todos [('Locate a demo-stub add capability (not curren', 'completed'), ('Echo the computed result using demo-stub echo', 'in_progress'), ('Report both the addition result and the echo ', 'pending')]
plan event seq 11 mode agentic todos [('Locate a demo-stub add capability (not curren', 'completed'), ('Echo the computed result using demo-stub echo', 'completed'), ('Report both the addition result and the echo ', 'completed')]
# end — 2026-09-10T01:36:56Z
```
