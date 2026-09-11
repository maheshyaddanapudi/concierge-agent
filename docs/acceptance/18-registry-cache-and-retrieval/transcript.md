```
[   0.0s] # 18-registry-cache-and-retrieval — 2026-09-11T21:32:02.563Z
[   0.0s] settings ← {"registry_cache_mode":"bypass","default_model_params":null}
[   2.3s] bypass: bypass tools:g40 skills:g68 sub_agents:g74 settings:g51
[   2.5s] shot 00-cache-bypass-status.png
[   4.0s] memory: memory tools:g40/37 skills:g68/9 sub_agents:g74/5 settings:g52/116
[   4.2s] shot 01-cache-memory-live.png
[   4.2s] settings ← {"orchestrator_mode":"graph"}
[   6.2s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  23.5s] run f8828fc5-ae48-4525-ac17-1897950f632d → completed after 15s
[  23.5s] run f8828fc5-ae48-4525-ac17-1897950f632d → completed after 0s
[  24.7s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  24.8s] shot 02-graph-run-memory-mode.png
[  24.9s] settings ← {"orchestrator_mode":"agentic"}
[  26.9s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  38.1s] run 13617b35-1477-4fbe-a518-e173e89335ad → completed after 9s
[  38.1s] run 13617b35-1477-4fbe-a518-e173e89335ad → completed after 0s
[  39.3s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[  39.4s] shot 03-agentic-run-memory-mode.png
[  40.3s] skills generation after a write: 68 → 69
[  42.7s] shot 04-generation-bumped.png
[  44.2s] after refresh-all: tools:g41/37 skills:g71/9 sub_agents:g78/5 settings:g55/116
[  44.4s] shot 05-refresh-all.png
[  46.0s] Threshold: the field did not commit (30) — set through the API
[  46.1s] settings ← {"retrieval_threshold":1}
[  47.0s] retrieval: enabled=true threshold=1 top_k=1 embedding_model=null
[  47.6s] shot 06-retrieval-enabled.png
[  47.6s] settings ← {"orchestrator_mode":"graph"}
[  49.7s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  67.9s] run 606994be-d3c3-4e23-bbfb-ac1a6f5d2ad8 → completed after 16s
[  68.0s] run 606994be-d3c3-4e23-bbfb-ac1a6f5d2ad8 → completed after 0s
[  69.2s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  69.3s] shot 07-run-with-retrieval-active.png
[  69.4s] backend log: {"kind": "sub_agents", "total": 5, "shown": 1, "dropped": 4, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-11T21:32:52.357472Z"}
[  69.4s] settings ← {"retrieval_enabled":false,"retrieval_threshold":30,"retrieval_top_k":10}
[  73.0s] shot 08-back-to-bypass.png
[  76.1s] tools header: cache: memory · 37 records · gen 41 · loaded 1s ago
[  76.3s] shot 09-tools-cache-header-memory.png
[  81.6s] tools generation after the exposure toggle: 41 → 42; header: cache: memory · 37 records · gen 42 · loaded 6s ago
[  81.8s] shot 10-generation-bumped-after-toggle.png
[  84.1s] settings ← {"registry_cache_mode":"bypass"}
[  84.1s] settings ← {"orchestrator_mode":"graph"}
[  86.2s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 103.4s] run c1c1db12-55aa-409c-96db-68d3979d8027 → completed after 15s
[ 103.4s] run c1c1db12-55aa-409c-96db-68d3979d8027 → completed after 0s
[ 104.6s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[ 104.8s] shot 11-bypass-graph-run.png
[ 104.8s] settings ← {"orchestrator_mode":"agentic"}
[ 106.9s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 120.0s] run be315eca-8879-40e7-9fca-31e51442b4da → completed after 11s
[ 120.0s] run be315eca-8879-40e7-9fca-31e51442b4da → completed after 0s
[ 121.2s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[ 121.4s] shot 12-bypass-agentic-run.png
[ 126.7s] redis: mode=redis tools:g43/37 skills:g73/9 sub_agents:g80/5 settings:g66/116
[ 126.8s] shot 13-cache-redis-status.png
[ 126.8s] settings ← {"registry_cache_mode":"memory","orchestrator_mode":"graph"}
[ 126.8s] restored registry_cache_mode=memory
[ 126.8s] # end — 2026-09-11T21:34:09.403Z
```
