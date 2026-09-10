# §14q-94 — the M49 load scenarios at N=3 against N=1

The harness in `experiments/load/` driven through the balancer (the frontend nginx at :5174, which resolves `backend` per request), fake provider, `run_max_concurrent` as shipped. `GET /replicas` publishes the budget the peak is checked against.

## N=3

```
# M54 load — n3 — 2026-09-03T00:52:35Z — through http://localhost:5174

$ GET /replicas (the fleet and the budget before the run)
live: ['441e81a1fa4b', 'c9d74f7efd7e', 'd0428404618c']
budget: {'per_replica': 29, 'pool': 5, 'overflow': 10, 'checkpointer': 10, 'sessions': 4, 'replicas': 3, 'reserved': 10, 'needed': 97, 'declared_max': 100, 'fits': True, 'max_replicas_at_declared': 3}

$ psql: max_connections and the connections in use before
max_connections=100
in_use=43

$ harness.py --scenarios api,chat --chat-concurrency 5,10,25 (fake provider; runs land on whichever replica nginx picks)
[00:52:35] at rest: {'connections': {'total': 42, 'idle': 42}, 'max_connections': 100}
[00:52:35] ── scenario api ──
[00:52:36] api GET /runs: p50 31.86 ms, errors {}
[00:52:36] api GET /conversations: p50 20.69 ms, errors {}
[00:52:37] api GET /skills: p50 23.2 ms, errors {}
[00:52:37] api GET /tools: p50 14.68 ms, errors {}
[00:52:38] api GET /settings: p50 12.54 ms, errors {}
[00:52:38] api GET /memories/recall: p50 24.36 ms, errors {}
[00:52:38] ── scenario chat ──
[00:52:38] chat: 5 concurrent runs on fake:scripted
[00:52:38] chat 5: statuses {'completed': 5} e2e p95 341.18 ms peak conns 42
[00:52:40] chat: 10 concurrent runs on fake:scripted
[00:52:41] chat 10: statuses {'completed': 10} e2e p95 742.55 ms peak conns 46
[00:52:43] chat: 25 concurrent runs on fake:scripted
[00:52:45] chat 25: statuses {'completed': 25} e2e p95 2178.73 ms peak conns 65
[00:52:47] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 40', 'runs': 'DELETE 40', 'conversations': 'DELETE 40'}
[00:52:47] restoring settings: ['default_model']
[00:52:47] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/load-n3.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/load-n3.md
harness took 12 s

$ the harness's tables
# Load baseline — m54-n3
Captured 2026-09-03T00:52:35+00:00 at commit `354974d` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 42.
## Read path at rest
| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 31.86 | 225.67 | 249.75 | 10726 | {} |
| GET /conversations | 20.69 | 181.45 | 230.63 | 1264 | {} |
| GET /skills | 23.2 | 129.18 | 161.79 | 22347 | {} |
| GET /tools | 14.68 | 109.19 | 132.03 | 25601 | {} |
| GET /settings | 12.54 | 126.08 | 159.81 | 3328 | {} |
| GET /memories/recall | 24.36 | 115.81 | 148.12 | 2 | {} |
Peak connections during the sweep: 47
## Concurrent chat runs (fake:scripted)
| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 5 | {'completed': 5} | 40.6 | 317.01 | 341.18 | 14.57 | 42 |
| 10 | {'completed': 10} | 50.66 | 694.51 | 742.55 | 13.38 | 46 |
| 25 | {'completed': 25} | 483.41 | 1663.7 | 2178.73 | 11.28 | 65 |

$ psql: where the runs executed (owner_replica of the harness's runs)
# end — 2026-09-03T00:52:47Z
```

## N=1

```
# M54 load — n1 — 2026-09-03T00:54:16Z — through http://localhost:5174

$ GET /replicas (the fleet and the budget before the run)
live: ['a23d789d445b']
budget: {'per_replica': 29, 'pool': 5, 'overflow': 10, 'checkpointer': 10, 'sessions': 4, 'replicas': 1, 'reserved': 10, 'needed': 39, 'declared_max': 100, 'fits': True, 'max_replicas_at_declared': 3}

$ psql: max_connections and the connections in use before
max_connections=100
in_use=13

$ 12 POST /chat through the balancer (fake provider) → owner_replica of each: the balancer spreads the run plane
a23d789d445b|queued|4
a23d789d445b|running|8

$ harness.py --scenarios api,chat --chat-concurrency 5,10,25 (fake provider; runs land on whichever replica nginx picks)
[00:54:24] at rest: {'connections': {'total': 12, 'idle': 12}, 'max_connections': 100}
[00:54:24] ── scenario api ──
[00:54:25] api GET /runs: p50 49.68 ms, errors {}
[00:54:25] api GET /conversations: p50 40.86 ms, errors {}
[00:54:26] api GET /skills: p50 48.39 ms, errors {}
[00:54:27] api GET /tools: p50 41.68 ms, errors {}
[00:54:27] api GET /settings: p50 27.71 ms, errors {}
[00:54:28] api GET /memories/recall: p50 68.4 ms, errors {}
[00:54:28] ── scenario chat ──
[00:54:28] chat: 5 concurrent runs on fake:scripted
[00:54:30] chat 5: statuses {'completed': 5} e2e p95 1798.77 ms peak conns 12
[00:54:32] chat: 10 concurrent runs on fake:scripted
[00:54:34] chat 10: statuses {'completed': 10} e2e p95 2000.68 ms peak conns 21
[00:54:36] chat: 25 concurrent runs on fake:scripted
[00:54:42] chat 25: statuses {'completed': 25} e2e p95 6073.55 ms peak conns 22
[00:54:44] cleanup: {'memory_embeddings': 'DELETE 0', 'memories': 'DELETE 0', 'run_steps': 'DELETE 40', 'runs': 'DELETE 40', 'conversations': 'DELETE 40'}
[00:54:44] restoring settings: ['default_model']
[00:54:44] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/load-n1.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/load-n1.md
harness took 20 s

$ the harness's tables
# Load baseline — m54-n1
Captured 2026-09-03T00:54:24+00:00 at commit `d186208` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 12.
## Read path at rest
| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 49.68 | 201.94 | 216.61 | 10726 | {} |
| GET /conversations | 40.86 | 190.0 | 207.39 | 3475 | {} |
| GET /skills | 48.39 | 209.95 | 231.72 | 22347 | {} |
| GET /tools | 41.68 | 174.99 | 192.36 | 25601 | {} |
| GET /settings | 27.71 | 191.23 | 210.11 | 3328 | {} |
| GET /memories/recall | 68.4 | 182.95 | 197.05 | 2 | {} |
Peak connections during the sweep: 18
## Concurrent chat runs (fake:scripted)
| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |
|---|---|---|---|---|---|---|
| 5 | {'completed': 5} | 155.65 | 1531.78 | 1798.77 | 2.78 | 12 |
| 10 | {'completed': 10} | 413.15 | 1740.85 | 2000.68 | 4.99 | 21 |
| 25 | {'completed': 25} | 656.32 | 5345.07 | 6073.55 | 4.04 | 22 |

# end — 2026-09-03T00:54:44Z
```
