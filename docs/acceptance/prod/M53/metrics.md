# §14p-86 — the dashboards show the incident — the /metrics half

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ PATCH /settings default_model=fake:scripted; POST /_fake/script error='429 rate limit exceeded'; POST /chat
{'status': 'failed', 'error': "provider rate-limited (429) after the port's retry budget — RuntimeError: 429 rate limit exceeded: retry later (model settings in play: defa"}

$ GET /metrics — the §10 labels on the step series (model, effort) and the port series
concierge_steps_total{effort="-",kind="-",model="openrouter:qwen/qwen3.8-max",source="-",status="completed",tier="orchestrator"} 5.0
concierge_llm_calls_total{model="qwen/qwen3.8-max",provider="openrouter",status="ok"} 14.0
concierge_llm_calls_total{model="scripted",provider="fake",status="ok"} 1.0
concierge_llm_calls_total{model="scripted",provider="fake",status="rate_limited"} 1.0
concierge_llm_latency_seconds_count{model="qwen/qwen3.8-max",provider="openrouter",status="ok"} 14.0
concierge_llm_latency_seconds_count{model="scripted",provider="fake",status="ok"} 1.0
concierge_llm_latency_seconds_count{model="scripted",provider="fake",status="rate_limited"} 1.0

$ GET /metrics — saturation, in-flight, backlog, loop errors, sse
concierge_db_pool_connections{state="capacity"} 15.0
concierge_db_pool_connections{state="checked_out"} 0.0
concierge_db_pool_connections{state="idle"} 5.0
concierge_db_pool_connections{state="overflow"} 0.0
concierge_db_pool_saturation 0.0
concierge_runs_in_flight{state="running"} 0.0
concierge_runs_in_flight{state="queued"} 0.0
concierge_run_slots 8.0
concierge_backlog_depth{queue="ambient_events"} 0.0
concierge_backlog_depth{queue="deliveries"} 4.0
```
