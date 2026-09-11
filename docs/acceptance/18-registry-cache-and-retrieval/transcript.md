```
[   0.0s] # 18-registry-cache-and-retrieval — 2026-09-11T01:32:52.731Z
[   0.1s] settings ← {"registry_cache_mode":"bypass","default_model_params":null}
[   2.4s] bypass: bypass tools:g35 skills:g39 sub_agents:g41 settings:g21
[   2.6s] shot 00-cache-bypass-status.png
[   4.1s] memory: memory tools:g35/35 skills:g39/9 sub_agents:g41/5 settings:g22/113
[   4.3s] shot 01-cache-memory-live.png
[   4.3s] settings ← {"orchestrator_mode":"graph"}
[   6.4s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  20.5s] run 465a4c92-3889-46d6-8a47-f83a694dff2e → completed after 12s
[  20.5s] run 465a4c92-3889-46d6-8a47-f83a694dff2e → completed after 0s
[  21.7s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  21.9s] shot 02-graph-run-memory-mode.png
[  21.9s] settings ← {"orchestrator_mode":"agentic"}
[  23.9s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  37.1s] run 3b21f330-5a22-46aa-a438-cb6462f46ead → completed after 11s
[  37.1s] run 3b21f330-5a22-46aa-a438-cb6462f46ead → completed after 0s
[  38.3s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[  38.4s] shot 03-agentic-run-memory-mode.png
[  39.3s] skills generation after a write: 39 → 40
[  41.6s] shot 04-generation-bumped.png
[  43.2s] after refresh-all: tools:g36/35 skills:g42/9 sub_agents:g45/5 settings:g25/113
[  43.3s] shot 05-refresh-all.png
[  45.0s] Threshold: the field did not commit (30) — set through the API
[  45.0s] settings ← {"retrieval_threshold":1}
[  46.0s] retrieval: enabled=true threshold=1 top_k=1 embedding_model=null
[  46.6s] shot 06-retrieval-enabled.png
[  46.7s] settings ← {"orchestrator_mode":"graph"}
[  48.7s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  70.0s] run 2b7d3fc9-a6f6-40fd-8be8-cebae358762d → completed after 19s
[  70.0s] run 2b7d3fc9-a6f6-40fd-8be8-cebae358762d → completed after 0s
[  71.2s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  71.4s] shot 07-run-with-retrieval-active.png
[  71.4s] backend log: {"kind": "sub_agents", "total": 5, "shown": 1, "dropped": 4, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-11T01:33:41.543641Z"}
{"kind": "tools", "total": 2, "shown": 1, "dropped": 1, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-11T01:33:41.543821Z"}
[  71.4s] settings ← {"retrieval_enabled":false,"retrieval_threshold":30,"retrieval_top_k":10}
[  75.0s] shot 08-back-to-bypass.png
[  78.2s] tools header: cache: memory · 35 records · gen 36 · loaded 1s ago
[  78.3s] shot 09-tools-cache-header-memory.png
[  83.7s] tools generation after the exposure toggle: 36 → 37; header: cache: memory · 35 records · gen 37 · loaded 6s ago
[  83.8s] shot 10-generation-bumped-after-toggle.png
[  86.1s] settings ← {"registry_cache_mode":"bypass"}
[  86.2s] settings ← {"orchestrator_mode":"graph"}
[  88.3s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 101.4s] run 88d18712-d5bb-4240-934e-f2ffee505183 → completed after 11s
[ 101.4s] run 88d18712-d5bb-4240-934e-f2ffee505183 → completed after 0s
[ 102.6s] graph run → completed; answer: No "add" tool exists in the sitefiles toolset — the only sitefiles capability ex; steps: plan::completed
[ 102.8s] shot 11-bypass-graph-run.png
[ 102.8s] settings ← {"orchestrator_mode":"agentic"}
[ 104.8s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 118.0s] run 78948dae-d08d-457f-9f05-8ebe3418c78b → completed after 11s
[ 118.0s] run 78948dae-d08d-457f-9f05-8ebe3418c78b → completed after 0s
[ 119.2s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[ 119.3s] shot 12-bypass-agentic-run.png
[ 124.6s] redis: mode=redis tools:g38/35 skills:g44/9 sub_agents:g47/5 settings:g37/113
[ 124.7s] shot 13-cache-redis-status.png
[ 124.8s] settings ← {"registry_cache_mode":"memory","orchestrator_mode":"graph"}
[ 124.8s] restored registry_cache_mode=memory
[ 124.8s] # end — 2026-09-11T01:34:57.515Z
```
