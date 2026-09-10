# §14p-88 — a dropped LISTEN connection is noticed and repaired

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ GET /metrics listener gauges (before)
concierge_listener_connected{channel="registry_cache_inv"} 1.0
concierge_listener_connected{channel="ambient_events"} 1.0

$ psql: the backend's LISTEN sessions (named concierge-listen:<channel> in pg_stat_activity)
5280|concierge-listen:ambient_events|idle
5262|concierge-listen:registry_cache_inv|idle

$ psql: pg_terminate_backend on every LISTEN session
5280|concierge-listen:ambient_events|t
5262|concierge-listen:registry_cache_inv|t
t+1s: concierge_listener_connected{channel="registry_cache_inv"} 0.0 concierge_listener_connected{channel="ambient_events"} 0.0 
t+2s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+3s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+4s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+5s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+6s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+7s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 
t+8s: concierge_listener_connected{channel="registry_cache_inv"} 1.0 concierge_listener_connected{channel="ambient_events"} 1.0 

$ GET /metrics listener gauges + reconnect counters (after)
concierge_listener_connected{channel="registry_cache_inv"} 1.0
concierge_listener_connected{channel="ambient_events"} 1.0
concierge_listener_reconnects_total{channel="registry_cache_inv"} 1.0
concierge_listener_reconnects_total{channel="ambient_events"} 1.0

$ backend log: listener_lost / listener_reconnected / cache_listener_reconnected
"event": "listener_lost", "level": "warning", "timestamp": "2026-09-02T02:51:15.817452Z"
"event": "listener_lost", "level": "warning", "timestamp": "2026-09-02T02:51:15.817867Z"
"event": "listener_started", "level": "info", "timestamp": "2026-09-02T02:51:16.884626Z"
"event": "listener_reconnected", "level": "info", "timestamp": "2026-09-02T02:51:16.884836Z"
"event": "cache_listener_reconnected", "level": "info", "timestamp": "2026-09-02T02:51:16.884934Z"
"event": "listener_started", "level": "info", "timestamp": "2026-09-02T02:51:16.885753Z"
"event": "listener_reconnected", "level": "info", "timestamp": "2026-09-02T02:51:16.885985Z"

$ psql: fresh LISTEN sessions (new pids)
5547|concierge-listen:ambient_events|idle
5546|concierge-listen:registry_cache_inv|idle

$ a fire after the gap is drained within seconds: the wake NOTIFY is heard on the fresh session (the tick alone would take ambient_tick_interval_s)
ambient_tick_interval_s = 15
fire → {'status': 'accepted', 'event_id': '3db36fd4-6f0f-4001-a05f-83155855f688'}
verdict 'fired' after 152 ms
cleanup DELETE routine → HTTP 204
```
