# §14p-86 — the dashboards show the incident: the load half

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, ambient on (the M51 soak routine keeps firing in the background). Prometheus and Grafana are the operator tooling under `docs/observability/` (not one of the three shipped services), brought up on the stack's network and provisioned from that directory. The burst is six chats on the live model under `run_max_concurrent=3`, sampled from `/metrics` every 3 s; the Prometheus instant queries are the ones the runbooks name; the dashboards are screenshotted afterwards (`05-grafana-saturation.png`, `06-grafana-llm.png`). Transcript verbatim (the sandbox path shortened to `$SCRATCH`).

```
$ docker compose -f docs/observability/docker-compose.observability.yml up -d
 Container observability-prometheus-1 Running 
 Container observability-grafana-1 Running 
prometheus + grafana ready after 1s

$ prometheus targets
[('concierge-backend', 'up', '')]

$ PATCH /settings: live model, run_max_concurrent=3 (so the queue is visible under a burst of 6)
HTTP 200

$ the semaphore is rebuilt only when the process is idle (M51: rebuilding mid-flight would orphan holders) — wait for running=0 before the burst so the new limit is the one in force
idle after 12s

$ burst: 6 chats on the live model (3 slots → 3 queued), sampled every 3 s
t+3s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+6s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+9s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 3.0 concierge_run_slots 3.0 
t+12s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 2.0 concierge_run_slots 3.0 
t+15s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 3.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+18s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 2.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
t+21s: concierge_db_pool_saturation 0.0 concierge_runs_in_flight{state="running"} 0.0 concierge_runs_in_flight{state="queued"} 0.0 concierge_run_slots 3.0 
harness exit 0
ALL_OK

$ GET /metrics — the incident signals after the burst
concierge_llm_calls_total{model="qwen/qwen3.8-max",provider="openrouter",status="ok"} 14.0
concierge_llm_latency_seconds_count{model="qwen/qwen3.8-max",provider="openrouter",status="ok"} 14.0
concierge_llm_latency_seconds_sum{model="qwen/qwen3.8-max",provider="openrouter",status="ok"} 99.41748181800358
concierge_db_pool_connections{state="capacity"} 15.0
concierge_db_pool_connections{state="checked_out"} 0.0
concierge_db_pool_connections{state="idle"} 5.0
concierge_db_pool_connections{state="overflow"} 0.0
concierge_db_pool_saturation 0.0
concierge_runs_in_flight{state="running"} 0.0
concierge_runs_in_flight{state="queued"} 0.0
concierge_run_slots 3.0
concierge_steps_total{effort="-",kind="-",model="openrouter:qwen/qwen3.8-max",source="-",status="completed",tier="orchestrator"} 7.0
concierge_backlog_depth{queue="ambient_events"} 0.0
concierge_backlog_depth{queue="deliveries"} 4.0
concierge_mcp_servers{state="connected"} 2.0
concierge_mcp_servers{state="reconnecting"} 0.0
concierge_mcp_servers{state="circuit_open"} 0.0
concierge_listener_connected{channel="registry_cache_inv"} 1.0
concierge_listener_connected{channel="ambient_events"} 1.0
concierge_sse_subscribers{stream="chat"} 0.0
concierge_spend_usd_today 0.363086

$ prometheus: instant queries
max(concierge_db_pool_saturation) → [({}, '0')]
sum by (status) (increase(concierge_llm_calls_total[10m])) → [({'status': 'ok'}, '35.462242857142854')]
histogram_quantile(0.95, sum by (le) (rate(concierge_llm_latency_seconds_bucket[10m]))) → [({}, '34.49999999999997')]
max_over_time(concierge_runs_in_flight{state="queued"}[10m]) → [({'instance': 'backend:8000', 'job': 'concierge-backend', 'service': 'concierge-agent', 'state': 'queued'}, '3')]

$ screenshots: grafana dashboards
shot 05-grafana-saturation
shot 06-grafana-llm
```
