# Load baseline — baseline

Captured 2026-09-10T21:29:28+00:00 at commit `d47015c` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 14.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 104.31 | 431.19 | 526.23 | 102034 | {} |
| GET /conversations | 57.8 | 209.71 | 220.6 | 10305 | {} |
| GET /skills | 48.89 | 173.19 | 177.86 | 28285 | {} |
| GET /tools | 40.47 | 147.4 | 161.44 | 37159 | {} |[21:29:34] runs-scale 1131 runs GET /runs: p50 12.46 ms, 51838 bytes
[21:29:34] runs-scale 1131 runs GET /conversations: p50 7.37 ms, 9542 bytes
[21:29:35] runs-scale 10131 runs GET /runs: p50 14.29 ms, 51838 bytes
[21:29:35] runs-scale 10131 runs GET /conversations: p50 10.18 ms, 9592 bytes
[21:29:35] ── scenario chat ──
[21:29:36] chat: 5 concurrent runs on fake:scripted
[21:29:36] chat 5: statuses {'completed': 5} e2e p95 921.15 ms peak conns 19
[21:29:38] chat: 10 concurrent runs on fake:scripted
[21:29:41] chat 10: statuses {'completed': 10} e2e p95 2189.8 ms peak conns 24
[21:29:43] chat: 25 concurrent runs on fake:scripted
[21:29:49] chat 25: statuses {'completed': 25} e2e p95 5910.16 ms peak conns 24
[21:29:51] chat: 50 concurrent runs on fake:scripted
[21:30:05] chat 50: statuses {'completed': 49, 'http_503': 1} e2e p95 14636.28 ms peak conns 24
[21:30:07] ── scenario sse ──
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 5 open, probe ok 3/3 p50 15.13 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 10 open, probe ok 3/3 p50 12.4 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 15 open, probe ok 3/3 p50 10.48 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 20 open, probe ok 3/3 p50 11.57 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 25 open, probe ok 3/3 p50 12.17 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 30 open, probe ok 3/3 p50 12.94 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 35 open, probe ok 3/3 p50 14.81 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 40 open, probe ok 3/3 p50 14.68 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 45 open, probe ok 3/3 p50 10.24 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 50 open, probe ok 3/3 p50 10.93 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 55 open, probe ok 3/3 p50 10.66 ms, conns 14
[21:30:08] sse /api/v1/chat/stream/15c41479-c1e0-4d0b-91e8-0cfba2411ee3: 60 open, probe ok 3/3 p50 14.23 ms, conns 14
[21:30:24] sse /api/v1/ambient/stream: 0 open, probe ok 3/3 p50 47.79 ms, conns 13
[21:30:41] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 30093', 'runs': 'DELETE 10090', 'conversations': 'DELETE 191'}
[21:30:41] restoring settings: ['default_model']
[21:30:41] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/baseline.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/baseline.md
harness took 73 s
no /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/baseline.md — the harness did not finish

$ harness --scenarios ambient --ambient-events 40 (the webhook backlog: 40 fires, time to drain, fired/held verdicts, run outcomes, connection peak)
[21:30:41] at rest: {'connections': {'total': 14, 'idle': 14}, 'max_connections': 100}
[21:30:41] ── scenario ambient ──
[21:31:47] ambient: fire codes {'202': 40}, drain 63.11s, verdicts {'fired': 40}, runs {'statuses': {'completed': 40}, 'all_terminal_after_s': 66.12}
[21:31:47] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 40', 'runs': 'DELETE 40', 'conversations': 'DELETE 40'}
[21:31:47] restoring settings: ['ambient_routine_events_per_hour', 'ambient_runs_per_day', 'default_model']
[21:31:47] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/ambient-burst.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/ambient-burst.md
## Ambient backlog

Fired 40 webhook events: codes {'202': 40}, fire p95 409.07 ms.
Drain of 40 accepted events: 63.11 s (0.63 events/s); verdicts {'fired': 40}.
Runs: {'completed': 40}, all terminal after 66.12 s; peak connections 24.


$ backend log since the burst: pool exhaustion lines (ambient_execute_failed / ambient_tick_failed / QueuePool limit) — the M49 contended run had 34, a clean run 0
matching lines: 0
(the contention itself — the test suite running beside the burst — is not reproduced here: docs/acceptance/prod/M49/ambient-burst-under-contention.md)

$ live-sample: harness --model openrouter:qwen/qwen3.8-max --scenarios chat --chat-concurrency 3,6 --chat-deadline 240 (the latency a user sees; the backend's own provider key)
[21:31:48] at rest: {'connections': {'total': 14, 'idle': 14}, 'max_connections': 100}
[21:31:48] ── scenario chat ──
[21:31:48] chat: 3 concurrent runs on openrouter:qwen/qwen3.8-max
[21:31:55] chat 3: statuses {'completed': 3} e2e p95 6726.13 ms peak conns 14
[21:31:57] chat: 6 concurrent runs on openrouter:qwen/qwen3.8-max
[21:32:03] chat 6: statuses {'completed': 6} e2e p95 6392.38 ms peak conns 22
[21:32:05] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 9', 'runs': 'DELETE 9', 'conversations': 'DELETE 9'}
[21:32:05] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/live-sample.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49/live-sample.md
## Concurrent chat runs (openrouter:qwen/qwen3.8-max)

| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 3 | {'completed': 3} | 26.89 | 5773.67 | 6726.13 | 0.44 | 14 |
| 6 | {'completed': 6} | 268.07 | 4824.61 | 6392.38 | 0.9 | 22 |


$ prompt golden sets: python -m app.prompts.check inside the shipped image
prompt golden sets: 24 prompts, 24 cases, 0 failed
exit=0

$ a deliberate regression (planner loses its no_confident_match sentence; router renames {conditions} → {choices}) fails the harness with the prompt, case and cause named — edited in the container, restored after
FAIL planner [refusal_and_shape_contract]
     - must_contain missing: 'set no_confident_match to true'
FAIL router [pick_index]
     - placeholder(s) ['choices'] in the file are not supplied by the case — the consumer's .format() would raise KeyError
prompt golden sets: 24 prompts, 24 cases, 2 failed
exit=1
restored: prompt golden sets: 24 prompts, 24 cases, 0 failed

$ ruff BLE/S triage — a lint proof on a dev checkout, not an API drill (docs/acceptance/prod/M49/ruff-triage.md)
All checks passed!
bare 'noqa: BLE001' markers left in app/: 0

$ docker compose up -d --force-recreate backend (fake provider off again)
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 6s at http://localhost:8000
# end — 2026-09-10T21:32:20Z — records under /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M49
