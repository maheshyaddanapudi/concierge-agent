# M53 ops drill — 2026-09-10T21:14:37Z — model openrouter:qwen/qwen3.8-max
PATCH /settings → openrouter:qwen/qwen3.8-max ambient True
warm-up run 991b94fe-63b2-409b-9088-9e24b777e093 → timeout (a completed run for the record-stream check; today's spend for the ceiling)

$ §14p-84 GET /ready, /health; docker compose pause db → /ready 503 degraded (db names the failure), /health 200; unpause → 200
 HTTP 000
 HTTP 000
 Container concierge-agent-db-1 Paused 
 HTTP 000 in 0.000135s
 HTTP 000
 Container concierge-agent-db-1 Unpaused 
 HTTP 000

$ psql: a run owned by ANOTHER replica (inserted directly, status=running)
ERROR:  invalid input syntax for type uuid: "9b518314-958e-4164-ac28-9a415e5c058e
INSERT 0 1"
LINE 1: ...ns,total_output_tokens) values (gen_random_uuid(),'9b518314-...
                                                             ^
run 

$ docker compose kill -s USR1 backend → /ready 503 draining, /health 200; POST /chat 503 + Retry-After; a stream on a run this process is not executing gets event: reconnect; a completed run's record streams from ?after=3 with no hint
 Container concierge-agent-backend-1 Killed 
 HTTP 000
 HTTP 000
ERROR:  invalid input syntax for type uuid: ""
LINE 1: delete from runs where id=''; delete from conversations wher...
                                  ^

$ docker compose up -d --force-recreate --no-deps backend (a drained process is replaced, never resumed)
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}

$ §14p-86 /metrics: the §10 labels on the step series, the port series, saturation, in-flight, backlog, MCP, listener, SSE, spend
(the scripted provider 429 needs the fake provider on the backend; the live series below stand on their own)
concierge_steps_total series: 0 | every one carries ['tier', 'kind', 'source', 'model', 'effort', 'status'] → True

(no series matching ^concierge_llm_calls_total|^concierge_llm_latency_seconds_count)
concierge_db_pool_connections{state="capacity"} 15.0
concierge_db_pool_connections{state="checked_out"} 1.0
concierge_db_pool_connections{state="idle"} 4.0
concierge_db_pool_connections{state="overflow"} 0.0
concierge_db_pool_saturation 0.06666666666666667
concierge_run_slots 0.0
concierge_backlog_depth{queue="ambient_events"} 0.0
concierge_backlog_depth{queue="deliveries"} 23.0
concierge_listener_connected{channel="registry_cache_inv"} 1.0
concierge_listener_connected{channel="concierge_control"} 1.0
concierge_spend_usd_today 0.0

$ §14p-85 psql: one finished and one protected row per retention table, aged 400 days
INSERT 0 2
INSERT 0 2
INSERT 0 2
ERROR:  duplicate key value violates unique constraint "pattern_instances_armed_uq"
DETAIL:  Key (rule_key, partition_key)=(m53, ) already exists.
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...,created_at,updated_at) values (gen_random_uuid(),'07919512-...
                                                             ^
ERROR:  duplicate key value violates unique constraint "auth_sessions_token_hash_key"
DETAIL:  Key (token_hash)=(m53hash-live) already exists.
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...ect count(*) from a2a_tasks where remote_agent_id='07919512-...
                                                             ^
rows seeded: 

$ GET /retention (gates as shipped: five off, auth_sessions on) — eligible counted regardless of the gate
ambient_events       enabled=False  days=30    eligible=2
deliveries           enabled=False  days=90    eligible=1
ambient_policies     enabled=False  days=365   eligible=2
pattern_instances    enabled=False  days=7     eligible=0
a2a_tasks            enabled=False  days=90    eligible=0
auth_sessions        enabled=True   days=7     eligible=0

$ POST /retention/run with the gates as shipped → only the expired session goes
{"deleted":{"ambient_events":0,"deliveries":0,"ambient_policies":0,"pattern_instances":0,"a2a_tasks":0,"auth_sessions":0}}
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...ect count(*) from a2a_tasks where remote_agent_id='07919512-...
                                                             ^
rows after: 

$ PATCH /settings: every retention gate on; POST /retention/run → exactly one row per table; the protected rows survive
HTTP 200
{"deleted":{"ambient_events":2,"deliveries":1,"ambient_policies":2,"pattern_instances":0,"a2a_tasks":0,"auth_sessions":0}}
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...ect count(*) from a2a_tasks where remote_agent_id='07919512-...
                                                             ^
rows after: 
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...a2a|'||state from a2a_tasks where remote_agent_id='07919512-...
                                                             ^
concierge_retention_deleted_total{table="ambient_events"} 2.0
concierge_retention_deleted_total{table="deliveries"} 1.0
concierge_retention_deleted_total{table="ambient_policies"} 2.0
gates back to the shipped defaults: HTTP 200
{"detail":"retention_deliveries_days must be an integer number of days between 1 and 3650"} HTTP 422
ERROR:  invalid input syntax for type uuid: "07919512-cb74-46e8-87c2-3c31d47c15a4
INSERT 0 1"
LINE 1: ...m53'; delete from a2a_tasks where remote_agent_id='07919512-...
                                                             ^
shot 01-settings-retention-gates.png

$ §14p-89 GET /spend (today's runs priced from the provider feed or overrides); GET /runs?limit=3 → cost_usd per run
{'day': '2026-09-10', 'usd_today': 0.956624, 'runs_today': 111, 'unpriced_tokens': 209334, 'by_kind': {'chat': 0.778143, 'direct': 0.110364, 'eval': 0.029637, 'ambient': 0.03848}, 'ceiling': {'enabled': False, 'usd_per_day': 0.0001, 'remaining': None, 'reached': False}}
[{'status': 'completed', 'total_input_tokens': 1812, 'total_output_tokens': 98, 'cost_usd': 0.002106, 'cost_priced': True}, {'status': 'completed', 'total_input_tokens': 1807, 'total_output_tokens': 72, 'cost_usd': 0.002023, 'cost_priced': True}, {'status': 'completed', 'total_input_tokens': 1811, 'total_output_tokens': 75, 'cost_usd': 0.002036, 'cost_priced': True}]

$ PATCH /settings: model_prices override for openrouter:qwen/qwen3.8-max, ceiling 0.0001 USD/day, gate ON → /spend reached → POST /chat 429 + Retry-After
{'spend_ceiling_enabled': True, 'spend_ceiling_usd_per_day': 0.0001, 'model_prices': {'openrouter:qwen/qwen3.8-max': {'input_per_m': 1.0, 'output_per_m': 3.0}}}
{'usd_today': 0.956624, 'runs_today': 111, 'ceiling': {'enabled': True, 'usd_per_day': 0.0001, 'remaining': 0.0, 'reached': True}}
HTTP/1.1 429 Too Many Requests
retry-after: 3600
{"detail":"spend ceiling reached: $0.9566 of $0.00 spent today (spend_ceiling_usd_per_day) — runs of every kind are refused until the UTC day rolls over or the ceiling is raised in Settings → Cost"}

$ ambient: POST /routines (webhook trigger) → token → fire → the drain HOLDS the fire on the event with the ceiling as the reason
event 25692e91-fd8c-4bf8-8a8c-3c4fb05c0b7d
t+5s: held | spend ceiling: spend ceiling reached: $0.9566 of $0.00 spent today (spend_ceiling_usd_per_day) — runs of every kind are refused until the UTC day rolls over or 
concierge_spend_usd_today 0.9566240000000001
concierge_spend_ceiling_refusals_total{kind="chat"} 1.0
concierge_spend_ceiling_refusals_total{kind="ambient"} 1.0

$ PATCH /settings spend_ceiling_enabled=false → POST /chat 201 (byte-identical admission), priced from the captured usage
HTTP 200
{"run_id":"5cc3596a-cce5-4e93-b979-0da5f05c86f9","conversation_id":"92e8eeff-7a4f-4b63-88dd-e1a70d63c2a1"} HTTP 201 
run 5cc3596a-cce5-4e93-b979-0da5f05c86f9 → completed
{'status': 'completed', 'total_input_tokens': 1813, 'total_output_tokens': 66, 'cost_usd': 0.002011, 'cost_priced': True}
shot 02-settings-cost-and-ceiling.png
shot 04-runs-cost-column.png

$ §14p-87 the seeded fetch server: SIGKILL its process inside the container (a /proc scan — the slim image has no pkill) → the health ping (mcp_health_interval_s) marks it error → auto-reconnect brings it back active
before: active |  | 1
t+5s: active |  | 1
t+10s: active |  | 1
t+15s: error | health ping failed | 1
t+20s: active |  | 1
t+25s: active |  | 1
t+30s: active |  | 1
t+35s: active |  | 1
t+40s: active |  | 1
t+45s: active |  | 1
"event": "mcp_ping_failed", "level": "warning", "timestamp": "2026-09-10T21:
"event": "mcp_reconnect_scheduled", "level": "info", "timestamp": "2026-09-10T21:17:
"event": "mcp_tools_ingested", "level": "info", "timestamp": "2026-09-10T21:17:
"event": "mcp_reconnected", "level": "info", "timestamp": "2026-09-10T21:17:
concierge_mcp_servers{state="connected"} 3.0
concierge_mcp_servers{state="reconnecting"} 0.0
concierge_mcp_servers{state="circuit_open"} 0.0
concierge_mcp_reconnects_total{outcome="ok"} 1.0

$ PATCH /settings mcp_reconnect_max_attempts=2; POST /mcp-servers stdio command=/bin/false → the breaker opens after two attempts; POST …/reconnect resets it
server 06c96c47-b466-4441-9414-1481a62ad23d
t+5s: error | BrokenResourceError
t+10s: error | BrokenResourceError
t+15s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+20s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+25s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+30s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+35s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+40s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
t+45s: error | circuit open after 2 failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually
concierge_mcp_servers{state="connected"} 3.0
concierge_mcp_servers{state="reconnecting"} 0.0
concierge_mcp_servers{state="circuit_open"} 1.0
concierge_mcp_reconnects_total{outcome="ok"} 1.0
concierge_mcp_reconnects_total{outcome="failed"} 2.0
concierge_mcp_reconnects_total{outcome="circuit_open"} 1.0
{"server_id": "06c96c47-b466-4441-9414-1481a62ad23d", "attempts": 2, "event": "mcp_circuit_open", "level": "warning", "timestamp": "2026-09-10T21:18:09.139797Z"
reconnect → error | BrokenResourceError (attempts restart from 0)
concierge_mcp_servers{state="connected"} 3.0
concierge_mcp_servers{state="reconnecting"} 1.0
concierge_mcp_servers{state="circuit_open"} 0.0
DELETE → HTTP 204

$ re-ingest keeps intent (the stub server shipped in the image): a tool set inactive stays inactive across refresh-tools; a deleted tool stays deleted across reconnect; POST /tools/{id}/restore brings it back
m53-stub: active |  | 4
Traceback (most recent call last):
  File "<string>", line 1, in <module>
IndexError: list index out of range
Traceback (most recent call last):
  File "<string>", line 1, in <module>
IndexError: list index out of range
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/usr/lib/python3.11/json/__init__.py", line 293, in load
    return loads(fp.read(),
           ^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/decoder.py", line 337, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/decoder.py", line 355, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/usr/lib/python3.11/json/__init__.py", line 293, in load
    return loads(fp.read(),
           ^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/decoder.py", line 337, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/json/decoder.py", line 355, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
DELETE add → HTTP 307
m53-stub.add-36aa82|active|deleted_at -|present
m53-stub.die-be29ea|active|deleted_at -|present
m53-stub.echo-1263cb|active|deleted_at -|present
m53-stub.mutate_toolset-733d76|active|deleted_at -|present
Traceback (most recent call last):
  File "<string>", line 1, in <module>
KeyError: 'tool_key'
cleanup DELETE stub → HTTP 204
shot 03-settings-mcp-reconnect.png

$ §14p-88 the supervised LISTEN sessions (application_name concierge-listen:<channel>): pg_terminate_backend on both → gauges 0 then 1, reconnect counters, new pids
concierge_listener_connected{channel="registry_cache_inv"} 1.0
concierge_listener_connected{channel="concierge_control"} 1.0
concierge_listener_connected{channel="ambient_events"} 1.0
ERROR:  ORDER BY position 2 is not in select list
LINE 1: ... where application_name like 'concierge-listen:%' order by 2
                                                                      ^
24866|concierge-listen:registry_cache_inv|true
24870|concierge-listen:concierge_control|true
24876|concierge-listen:ambient_events|true
t+1s: concierge_listener_connected{channel="registry_cache_inv"} 0.0 concierge_listener_connected{channel="concierge_control"} 0.0 concierge_listener_connected{channel="ambient_events"} 0.0 
t+2s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="concierge_control"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+3s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="concierge_control"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+4s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="concierge_control"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+5s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="concierge_control"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+6s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="concierge_control"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
concierge_listener_reconnects_total{channel="ambient_events"} 1.0
concierge_listener_reconnects_total{channel="registry_cache_inv"} 1.0
concierge_listener_reconnects_total{channel="concierge_control"} 1.0
      1 "event": "cache_listener_reconnected"
      3 "event": "listener_lost"
      3 "event": "listener_reconnected"
      3 "event": "listener_started"
ERROR:  ORDER BY position 2 is not in select list
LINE 1: ... where application_name like 'concierge-listen:%' order by 2
                                                                      ^

$ a fire after the gap is drained within seconds — the wake NOTIFY is heard on the fresh session (the tick alone would take ambient_tick_interval_s=15)
verdict 'fired' after 123 ms (psql polling at 100 ms adds its own latency)

$ §14p-86 load half: 6 chats on the live model under run_max_concurrent=3, sampled from /metrics every 3 s (Prometheus/Grafana from docs/observability/ are not part of the three shipped services — the dashboards stay in docs/acceptance/prod/M53/load-and-dashboards.md)
idle after 5s (the semaphore is rebuilt only when no run holds it)
t+3s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+6s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+9s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+12s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 2.0 concierge_run_slots 3.0 
t+15s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 2.0 concierge_run_slots 3.0 
t+18s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 2.0 concierge_run_slots 3.0 
t+21s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+24s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+27s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+30s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+33s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+36s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 1.0 concierge_run_slots 3.0 
t+39s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+42s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+45s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+48s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+51s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+54s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+57s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 1.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+60s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 1.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 

$ §14p-83 one-host half: a live run with an open curl stream; DEPLOY_SKIP_BUILD=1 DEPLOY_FORCE_RECREATE=1 DRAIN_WAIT_S=10 ./deploy.sh rolls the backend under it; the client reconnects with Last-Event-ID and resolves from the record (the 3-client harness report and the browser pass: deploy-drill.md, browser-deploy.md)
run a7794327-0149-43de-b084-d088728ffceb running; /ready before: {"status": "ready", "db": "ok", "accepting": true, "running": 1, "queued": 0, "max_concurrent": 8, "draining_since": null}
deploy:  Container concierge-agent-backend-1 Started 
deploy: backend ready (/ready 200)
deploy:  Container concierge-agent-frontend-1 Recreate 
deploy:  Container concierge-agent-frontend-1 Recreated 
deploy:  Container concierge-agent-frontend-1 Starting 
deploy:  Container concierge-agent-frontend-1 Started 
deploy: == deployed ==
deploy: {"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}
deploy.sh returned after 36 s
backend /ready 200 after 1s at http://localhost:8000
the stream saw ids up to 3 before the port closed (3 events)
reconnect with Last-Event-ID=3 on the new process:
id: 4 event: run_status
a7794327|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) — retr
non-terminal rows: 3
{"channel": "[redacted]_control", "pid": 25667, "event": "listener_started", "level": "info", "timestamp": "2026-09-10T21:20:42.062155Z"}
{"channel": "[redacted]_control", "connected": true, "event": "control_listener_started", "level": "info", "timestamp": "2026-09-10T21:20:42
{"channel": "ambient_events", "pid": 25672, "event": "listener_started", "level": "info", "timestamp": "2026-09-10T21:20:42.522181Z"}

$ §14p-90 one-host half: ./backup.sh (pg_dump -Fc + workspace tar) → ./restore.sh round trip into the running db (RTO printed by restore.sh); row counts, the pgvector indexes and a conversation byte-identical before and after
before: runs=120 run_steps=664 memories=24 memory_embeddings=0 ambient_events=13 deliveries=55 tools=60 memory_embeddings_pkey memory_embeddings_emb_1024_hnsw memory_embeddings_emb_1536_hnsw memory_embeddings_emb_256_hnsw memory_embeddings_emb_3072_hnsw memory_embeddings_emb_384_hnsw memory_embeddings_emb_512_hnsw memory_embeddings_emb_64_hnsw memory_embeddings_emb_768_hnsw memory_embeddings_model_idx 
database  /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M53/backups/concierge-20260910T212043Z.dump (2.2M)
workspace /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/prod/M53/backups/concierge-20260910T212043Z.workspace.tar (12K)
took 1 s
== stop backend (readiness first) ==
== restore database ==
pg_restore took 1 s (schema, data and every index, pgvector included)
== restore workspace ==
== start backend ==
== restored: RTO 9 s (stop → restore → ready) ==
backend /ready 200 after 1s at http://localhost:8000
after:  runs=120 run_steps=664 memories=24 memory_embeddings=0 ambient_events=13 deliveries=55 tools=60 memory_embeddings_pkey memory_embeddings_emb_1024_hnsw memory_embeddings_emb_1536_hnsw memory_embeddings_emb_256_hnsw memory_embeddings_emb_3072_hnsw memory_embeddings_emb_384_hnsw memory_embeddings_emb_512_hnsw memory_embeddings_emb_64_hnsw memory_embeddings_emb_768_hnsw memory_embeddings_model_idx 
GET /conversations/{id} byte-identical before/after: true
mcp servers: [('fetch', 'active'), ('filesystem', 'active'), ('sitefiles', 'active')]
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}
 Container concierge-agent-backend-1 Healthy 
# end — 2026-09-10T21:20:55Z
