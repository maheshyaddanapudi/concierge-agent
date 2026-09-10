```
[   0.0s] # 18-registry-cache-and-retrieval — 2026-09-10T03:09:16.461Z
[   0.0s] settings ← {"registry_cache_mode":"bypass","default_model_params":null}
[   2.2s] bypass: bypass tools:g8 skills:g14 sub_agents:g17 settings:g35
[   2.4s] shot 00-cache-bypass-status.png
[   3.9s] memory: memory tools:g8/29 skills:g14/7 sub_agents:g17/4 settings:g36/110
[   4.1s] shot 01-cache-memory-live.png
[   4.1s] settings ← {"orchestrator_mode":"graph"}
[   6.1s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  24.4s] run a2995235-7a43-47ac-bba4-062125eba0bd → completed after 16s
[  24.4s] run a2995235-7a43-47ac-bba4-062125eba0bd → completed after 0s
[  25.6s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  25.8s] shot 02-graph-run-memory-mode.png
[  25.8s] settings ← {"orchestrator_mode":"agentic"}
[  27.8s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  65.3s] run 85cfb66b-3e37-4b9c-be33-d78f16509ff7 → completed after 35s
[  65.3s] run 85cfb66b-3e37-4b9c-be33-d78f16509ff7 → completed after 0s
[  66.5s] agentic run → completed; answer: 42; steps: route::completed route::completed skill::completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed aggregate::completed
[  66.7s] shot 03-agentic-run-memory-mode.png
[  67.5s] skills generation after a write: 14 → 15
[  69.9s] shot 04-generation-bumped.png
[  71.5s] after refresh-all: tools:g9/29 skills:g17/7 sub_agents:g21/4 settings:g39/110
[  71.7s] shot 05-refresh-all.png
[  73.3s] Threshold: the field did not commit (30) — set through the API
[  73.4s] settings ← {"retrieval_threshold":1}
[  74.3s] retrieval: enabled=true threshold=1 top_k=1 embedding_model=null
[  74.9s] shot 06-retrieval-enabled.png
[  75.0s] settings ← {"orchestrator_mode":"graph"}
[  77.0s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  97.2s] run 83abf87a-8962-4bb6-acf9-d0bd9d2d0a66 → completed after 18s
[  97.2s] run 83abf87a-8962-4bb6-acf9-d0bd9d2d0a66 → completed after 0s
[  98.4s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  98.6s] shot 07-run-with-retrieval-active.png
[  98.7s] backend log: {"kind": "sub_agents", "total": 4, "shown": 1, "dropped": 3, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-10T03:10:33.504424Z"}
[  98.7s] settings ← {"retrieval_enabled":false,"retrieval_threshold":30,"retrieval_top_k":10}
[ 102.3s] shot 08-back-to-bypass.png
[ 105.0s] tools header: cache: memory · 29 records · gen 9 · loaded 1s ago
[ 105.2s] shot 09-tools-cache-header-memory.png
[ 108.4s] tools generation after the exposure toggle: 9 → 10; header: cache: memory · 29 records · gen 9 · loaded 5s ago
[ 108.6s] shot 10-generation-bumped-after-toggle.png
[ 111.0s] settings ← {"registry_cache_mode":"bypass"}
[ 111.1s] settings ← {"orchestrator_mode":"graph"}
[ 113.1s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 132.3s] run dd5d583f-8f9a-40c4-805d-912ac42aff18 → completed after 17s
[ 132.3s] run dd5d583f-8f9a-40c4-805d-912ac42aff18 → completed after 0s
[ 133.5s] graph run → completed; answer: 42; steps: plan::completed
[ 133.7s] shot 11-bypass-graph-run.png
[ 133.7s] settings ← {"orchestrator_mode":"agentic"}
[ 135.7s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 155.0s] run a18b55f1-b95a-41d2-8dc5-5bd18afae39c → completed after 17s
[ 155.0s] run a18b55f1-b95a-41d2-8dc5-5bd18afae39c → completed after 0s
[ 156.2s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[ 156.3s] shot 12-bypass-agentic-run.png
[ 161.5s] redis: mode=redis tools:g11/29 skills:g19/7 sub_agents:g23/4 settings:g50/110
[ 161.7s] shot 13-cache-redis-status.png
[ 161.8s] settings ← {"registry_cache_mode":"memory","orchestrator_mode":"graph"}
[ 161.8s] restored registry_cache_mode=memory
[ 161.8s] # end — 2026-09-10T03:11:58.219Z
```
