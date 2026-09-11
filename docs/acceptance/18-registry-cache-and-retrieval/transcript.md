```
[   0.0s] # 18-registry-cache-and-retrieval — 2026-09-11T22:37:22.731Z
[   0.1s] settings ← {"registry_cache_mode":"bypass","default_model_params":null}
[   2.4s] bypass: bypass tools:g41 skills:g58 sub_agents:g65 settings:g29
[   2.6s] shot 00-cache-bypass-status.png
[   4.1s] memory: memory tools:g41/37 skills:g58/9 sub_agents:g65/5 settings:g30/116
[   4.3s] shot 01-cache-memory-live.png
[   4.3s] settings ← {"orchestrator_mode":"graph"}
[   6.3s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  21.5s] run 47c07934-1534-4fcc-a72a-330714ebde52 → completed after 13s
[  21.5s] run 47c07934-1534-4fcc-a72a-330714ebde52 → completed after 0s
[  22.7s] graph run → completed; answer: 42; steps: plan::completed
[  22.9s] shot 02-graph-run-memory-mode.png
[  22.9s] settings ← {"orchestrator_mode":"agentic"}
[  24.9s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  38.4s] run 90392d98-81ef-4fcd-a1ac-bc6b2a484020 → completed after 11s
[  38.4s] run 90392d98-81ef-4fcd-a1ac-bc6b2a484020 → completed after 0s
[  39.6s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[  39.7s] shot 03-agentic-run-memory-mode.png
[  40.5s] skills generation after a write: 58 → 59
[  42.9s] shot 04-generation-bumped.png
[  44.5s] after refresh-all: tools:g42/37 skills:g61/9 sub_agents:g69/5 settings:g33/116
[  44.6s] shot 05-refresh-all.png
[  46.3s] Threshold: the field did not commit (30) — set through the API
[  46.3s] settings ← {"retrieval_threshold":1}
[  47.3s] retrieval: enabled=true threshold=1 top_k=1 embedding_model=null
[  47.9s] shot 06-retrieval-enabled.png
[  47.9s] settings ← {"orchestrator_mode":"graph"}
[  50.0s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  68.2s] run 7c2e4df2-8f91-4db2-98e3-6ea67ce9d7a2 → completed after 16s
[  68.2s] run 7c2e4df2-8f91-4db2-98e3-6ea67ce9d7a2 → completed after 0s
[  69.4s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  69.6s] shot 07-run-with-retrieval-active.png
[  69.6s] backend log: {"kind": "sub_agents", "total": 5, "shown": 1, "dropped": 4, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-11T22:38:12.805826Z"}
{"kind": "tools", "total": 2, "shown": 1, "dropped": 1, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-11T22:38:12.806072Z"}
[  69.6s] settings ← {"retrieval_enabled":false,"retrieval_threshold":30,"retrieval_top_k":10}
[  73.3s] shot 08-back-to-bypass.png
[  76.4s] tools header: cache: memory · 37 records · gen 42 · loaded 1s ago
[  76.6s] shot 09-tools-cache-header-memory.png
[  81.9s] tools generation after the exposure toggle: 42 → 43; header: cache: memory · 37 records · gen 43 · loaded 6s ago
[  82.1s] shot 10-generation-bumped-after-toggle.png
[  84.5s] settings ← {"registry_cache_mode":"bypass"}
[  84.5s] settings ← {"orchestrator_mode":"graph"}
[  86.6s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 104.8s] run 524f7d1a-9b01-49cf-a19f-a7bd056b8f07 → completed after 16s
[ 104.8s] run 524f7d1a-9b01-49cf-a19f-a7bd056b8f07 → completed after 0s
[ 106.0s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[ 106.1s] shot 11-bypass-graph-run.png
[ 106.1s] settings ← {"orchestrator_mode":"agentic"}
[ 108.2s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 121.3s] run eb73dcd0-2fe1-4279-a0c4-ca52d39b9e47 → completed after 11s
[ 121.3s] run eb73dcd0-2fe1-4279-a0c4-ca52d39b9e47 → completed after 0s
[ 122.5s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[ 122.7s] shot 12-bypass-agentic-run.png
[ 128.0s] redis: mode=redis tools:g44/37 skills:g63/9 sub_agents:g71/5 settings:g45/116
[ 128.1s] shot 13-cache-redis-status.png
[ 128.1s] settings ← {"registry_cache_mode":"bypass","orchestrator_mode":"graph"}
[ 128.1s] restored registry_cache_mode=bypass
[ 128.1s] # end — 2026-09-11T22:39:30.860Z
```
