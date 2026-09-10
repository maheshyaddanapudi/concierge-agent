# §14q-96 — three replicas cold-boot together

Transcript of the sandbox driver (`curl`, `psql`, `docker`) on a fresh volume, `docker compose up -d --scale backend=3` with `DB_REPLICAS=3`. The boot section first, then the drill.

```
# M54 fleet — cold boot of three replicas — 2026-09-03T00:30:30Z

$ docker compose down -v (a fresh volume: migrations and seeds must apply exactly once across the three)
 Network concierge-agent_default Resource is still in use 
 Volume concierge-agent_pgdata Removed 
 Volume concierge-agent_workspace Removed 

$ webhook receiver container on the stack network (m54-hook:9099)
 Container concierge-agent-db-1 Started 
 Container concierge-agent-redis-1 Started 

$ docker compose up -d --scale backend=3 backend frontend  (T0=00:30:35)
 Container concierge-agent-backend-3 Healthy 
 Container concierge-agent-backend-2 Healthy 
 Container concierge-agent-backend-1 Healthy 
 Container concierge-agent-frontend-1 Starting 
 Container concierge-agent-frontend-1 Started 
backend-1 ready after 1s on host port 8005
backend-2 ready after 1s on host port 8004
backend-3 ready after 1s on host port 8003
all three /ready 200 at +14 s

# §14q-96 — three replicas cold-boot together — 2026-09-03T00:30:49Z

$ the three replicas, their host ports and their replica ids
backend-1 → :8005 → a4ce73f85ce8
backend-2 → :8004 → f418f753000e
backend-3 → :8003 → 707b16c047dd

$ GET /replicas via replica 1 (the fleet as the database sees it)
self a4ce73f85ce8 control_listener True
  707b16c047dd live True subscribers 0 runs 0
  f418f753000e live True subscribers 0 runs 0
  a4ce73f85ce8 live True subscribers 0 runs 0
budget {'per_replica': 29, 'pool': 5, 'overflow': 10, 'checkpointer': 10, 'sessions': 4, 'replicas': 3, 'reserved': 10, 'needed': 97, 'declared_max': 100, 'fits': True, 'max_replicas_at_declared': 3}

$ boot lock, migrations and seed in the three logs (who migrated, who waited)
-- backend-1: alembic 'Running upgrade' lines = 0, seed lines = 0
replica": "a4ce73f85ce8", "per_replica": 29, "pool": 5, "overflow": 10, "checkpointer": 10, "sessions": 4, "replicas": 3, "reserved": 10, "needed": 97, "declared_max": 100, "fits": true, "max_replicas
channel": "[redacted]_control", "connected": true, "event": "control_listener_started" @ 2026-09-03T00:30:43.111440Z
-- backend-2: alembic 'Running upgrade' lines = 0, seed lines = 0
replica": "f418f753000e", "per_replica": 29, "pool": 5, "overflow": 10, "checkpointer": 10, "sessions": 4, "replicas": 3, "reserved": 10, "needed": 97, "declared_max": 100, "fits": true, "max_replicas
channel": "[redacted]_control", "connected": true, "event": "control_listener_started" @ 2026-09-03T00:30:42.103850Z
-- backend-3: alembic 'Running upgrade' lines = 25, seed lines = 0
replica": "707b16c047dd", "per_replica": 29, "pool": 5, "overflow": 10, "checkpointer": 10, "sessions": 4, "replicas": 3, "reserved": 10, "needed": 97, "declared_max": 100, "fits": true, "max_replicas
channel": "[redacted]_control", "connected": true, "event": "control_listener_started" @ 2026-09-03T00:30:41.488283Z

$ psql: alembic head, seeded MCP servers, tools per server (each tool exactly once)
s8g9h0i1j2k3
fetch|stdio|active|static
filesystem|stdio|active|static
fetch|1|1
filesystem|14|14
duplicates=0

$ every replica reports every server connected (per-replica MCP gauge + GET /mcp-servers)
backend-1: concierge_mcp_servers{state="connected"} 2.0 concierge_mcp_servers{state="reconnecting"} 0.0 concierge_mcp_servers{state="circuit_open"} 0.0 
    [('fetch', 'active', 1), ('filesystem', 'active', 14)]
backend-2: concierge_mcp_servers{state="connected"} 2.0 concierge_mcp_servers{state="reconnecting"} 0.0 concierge_mcp_servers{state="circuit_open"} 0.0 
    [('fetch', 'active', 1), ('filesystem', 'active', 14)]
backend-3: concierge_mcp_servers{state="connected"} 2.0 concierge_mcp_servers{state="reconnecting"} 0.0 concierge_mcp_servers{state="circuit_open"} 0.0 
    [('fetch', 'active', 1), ('filesystem', 'active', 14)]

$ PATCH /settings mcp_health_interval_s=5, registry_cache_mode=memory (via replica 1)
{'mcp_health_interval_s': 5, 'registry_cache_mode': 'memory'}
(30 s: the health loops finish the sleep they started under the old 30 s interval and pick up 5 s)

$ POST /mcp-servers m54-stub via replica 1 → the other two connect it within a health interval (5 s)
stub id f9a8f086-e7d8-4747-9f50-61c8827631b9
replicas 2 and 3 log the stub after 3348 ms
-- backend-1
"mcp_connected", "level": "info", "timestamp": "2026-09-03T00:31:21.997008Z"}
-- backend-2
"mcp_connected", "level": "info", "timestamp": "2026-09-03T00:31:24.572931Z"}
-- backend-3
"mcp_connected", "level": "info", "timestamp": "2026-09-03T00:31:23.830605Z"}
m54-stub.add|active|present
m54-stub.die|active|present
m54-stub.echo|active|present
m54-stub.mutate_toolset|active|present
stub duplicates=0

$ a registry write on replica 2 (PATCH the stub's echo tool → inactive) invalidates replicas 1 and 3: GET /cache/status on each
before:
  backend-1 memory tools gen 9 dirty True records 25
  backend-2 memory tools gen 9 dirty True records 25
  backend-3 memory tools gen 9 dirty True records 25
PATCH → m54-stub.echo inactive
immediately after (the NOTIFY landed; the generation moved; dirty until the next read reloads):
  backend-1 tools gen 10 dirty True
  backend-2 tools gen 10 dirty True
  backend-3 tools gen 10 dirty True
(the cache is read by the run plane — the tools projection — not by the REST list, which reads the table; one fake-provider chat on 1 and on 3 reloads them)
after a run on 1 and 3 (reloaded under the new generation; 2 reloads on its own next read):
  backend-1 tools gen 10 dirty False records 29
  backend-2 tools gen 10 dirty True records 25
  backend-3 tools gen 10 dirty False records 29
backend-1 sees echo: ['inactive']
backend-2 sees echo: ['inactive']
backend-3 sees echo: ['inactive']

$ cleanup: DELETE the stub via replica 3; cache mode back to bypass
DELETE → HTTP 204
# end §96 — 2026-09-03T00:31:29Z
```
