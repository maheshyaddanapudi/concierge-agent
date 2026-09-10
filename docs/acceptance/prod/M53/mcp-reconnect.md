# §14p-87 — an MCP server that dies comes back; a broken one stops being retried; re-ingest keeps intent

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ GET /mcp-servers fetch → status (before)
{'name': 'fetch', 'status': 'active', 'last_error': None, 'tool_count': 1}

$ kill -9 every mcp-server-fetch process inside the backend container (python scan of /proc; the slim image has no pkill)

$ poll GET /mcp-servers fetch every 5 s: error (health ping) → active (auto reconnect)
t+5s: active | 
t+10s: active | 
t+15s: active | 
t+20s: active | 
t+25s: error | health ping failed
t+30s: active | 

$ backend log: mcp_ping_failed → mcp_reconnect_scheduled → mcp_reconnected
"event": "mcp_ping_failed", "level": "warning", "timestamp": "2026-09-02T02:51:43.606149Z"
"event": "mcp_reconnect_scheduled", "level": "info", "timestamp": "2026-09-02T02:51:43.615574Z"
"event": "mcp_tools_ingested", "level": "info", "timestamp": "2026-09-02T02:51:49.301441Z"
"event": "mcp_reconnected", "level": "info", "timestamp": "2026-09-02T02:51:49.306713Z"

$ GET /metrics mcp series
concierge_mcp_servers{state="connected"} 2.0
concierge_mcp_servers{state="reconnecting"} 0.0
concierge_mcp_servers{state="circuit_open"} 0.0
concierge_mcp_reconnects_total{outcome="ok"} 1.0

$ PATCH /settings mcp_reconnect_max_attempts=2; POST /mcp-servers stdio command=/bin/false (cannot start)
server 24d6d9f5-1ddf-43b0-bfe4-cf22f5d80e71
t+5s: error | McpError: Connection closed
t+10s: error | BrokenResourceError
t+15s: error | BrokenResourceError
t+20s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+25s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+30s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+35s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+40s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+45s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually

$ GET /metrics circuit_open
concierge_mcp_servers{state="circuit_open"} 1.0
concierge_mcp_reconnects_total{outcome="ok"} 1.0
concierge_mcp_reconnects_total{outcome="failed"} 2.0
concierge_mcp_reconnects_total{outcome="circuit_open"} 1.0

$ backend log: mcp_circuit_open
"event": "mcp_circuit_open", "level": "warning", "timestamp": "2026-09-02T02:52:05.302260Z"

$ POST /mcp-servers/24d6d9f5-1ddf-43b0-bfe4-cf22f5d80e71/reconnect → the operator resets the breaker (it fails again, attempts restart from 0)
{'status': 'error', 'last_error': 'McpError: Connection closed'}
concierge_mcp_servers{state="reconnecting"} 1.0
concierge_mcp_servers{state="circuit_open"} 0.0
DELETE → HTTP 204

$ POST /mcp-servers stdio: the test stub server shipped in the image (echo, add, …)
{'status': 'active', 'tool_count': 4, 'last_error': None}

$ PATCH /tools/838c3c71-a953-4e70-abe4-81c5276019c3 status=inactive (the operator's word)
{'tool_key': 'm53-stub.echo', 'status': 'inactive', 'ingest_state': 'present'}

$ POST /mcp-servers/87328421-7bd7-45dd-b88e-7aaf9aaf4897/refresh-tools → echo stays inactive
{'tool_key': 'm53-stub.echo', 'status': 'inactive', 'ingest_state': 'present'}

$ DELETE /tools/b5048fc9-209d-4662-889e-8155e9a24648 (soft delete) → POST /mcp-servers/87328421-7bd7-45dd-b88e-7aaf9aaf4897/reconnect → still deleted
HTTP 204
[{'tool_key': 'm53-stub.add', 'status': 'active', 'deleted_at': '2026-09-02T02:52:40.466412Z', 'ingest_state': 'present'}, {'tool_key': 'm53-stub.echo', 'status': 'inactive', 'deleted_at': None, 'ingest_state': 'present'}]

$ POST /tools/b5048fc9-209d-4662-889e-8155e9a24648/restore
{'tool_key': 'm53-stub.add', 'status': 'active', 'deleted_at': None}
cleanup DELETE stub → HTTP 204
```
