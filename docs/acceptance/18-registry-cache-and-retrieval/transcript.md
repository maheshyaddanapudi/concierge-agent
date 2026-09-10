```
[   0.0s] # 18-registry-cache-and-retrieval — 2026-09-10T18:18:19.172Z
[   0.0s] settings ← {"registry_cache_mode":"bypass","default_model_params":null}
[   2.3s] bypass: bypass tools:g3 skills:g3 sub_agents:g3 settings:g6
[   2.5s] shot 00-cache-bypass-status.png
[   4.1s] memory: memory tools:g3/29 skills:g3/7 sub_agents:g3/5 settings:g7/110
[   4.2s] shot 01-cache-memory-live.png
[   4.3s] settings ← {"orchestrator_mode":"graph"}
[   6.4s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  31.8s] run 4a27653b-779b-4731-98fe-4c71616a2b8f → completed after 23s
[  31.8s] run 4a27653b-779b-4731-98fe-4c71616a2b8f → completed after 0s
[  33.0s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  33.2s] shot 02-graph-run-memory-mode.png
[  33.2s] settings ← {"orchestrator_mode":"agentic"}
[  35.3s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  51.6s] run 53333cda-7bd6-493e-9ffb-562f6255ce71 → completed after 14s
[  51.6s] run 53333cda-7bd6-493e-9ffb-562f6255ce71 → completed after 0s
[  52.8s] agentic run → completed; answer: 42; steps: aggregate::completed
[  53.0s] shot 03-agentic-run-memory-mode.png
[  53.8s] skills generation after a write: 3 → 4
[  56.3s] shot 04-generation-bumped.png
[  57.8s] after refresh-all: tools:g4/29 skills:g6/7 sub_agents:g7/5 settings:g10/110
[  58.0s] shot 05-refresh-all.png
[  59.7s] Threshold: the field did not commit (30) — set through the API
[  59.7s] settings ← {"retrieval_threshold":1}
[  60.7s] retrieval: enabled=true threshold=1 top_k=1 embedding_model=null
[  61.3s] shot 06-retrieval-enabled.png
[  61.4s] settings ← {"orchestrator_mode":"graph"}
[  63.5s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  86.9s] run 6a17b246-460c-4185-b2be-b5e9da433ef6 → completed after 21s
[  86.9s] run 6a17b246-460c-4185-b2be-b5e9da433ef6 → completed after 0s
[  88.1s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[  88.3s] shot 07-run-with-retrieval-active.png
[  88.3s] backend log: {"kind": "sub_agents", "total": 5, "shown": 1, "dropped": 4, "event": "retrieval_truncated_catalog", "level": "info", "timestamp": "2026-09-10T18:19:22.748707Z"}
[  88.3s] settings ← {"retrieval_enabled":false,"retrieval_threshold":30,"retrieval_top_k":10}
[  92.0s] shot 08-back-to-bypass.png
[  95.2s] tools header: cache: memory · 29 records · gen 4 · loaded 1s ago
[  95.4s] shot 09-tools-cache-header-memory.png
[ 100.9s] tools generation after the exposure toggle: 4 → 5; header: cache: memory · 29 records · gen 5 · loaded 6s ago
[ 101.1s] shot 10-generation-bumped-after-toggle.png
[ 103.4s] settings ← {"registry_cache_mode":"bypass"}
[ 103.6s] settings ← {"orchestrator_mode":"graph"}
[ 105.7s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 130.1s] run 8307196a-ea8d-47f5-8584-6fc5fd59aabe → completed after 22s
[ 130.1s] run 8307196a-ea8d-47f5-8584-6fc5fd59aabe → completed after 0s
[ 131.3s] graph run → completed; answer: 42; steps: plan::completed route::completed skill::completed tool_call:sitefiles_add:completed aggregate::completed
[ 131.5s] shot 11-bypass-graph-run.png
[ 131.5s] settings ← {"orchestrator_mode":"agentic"}
[ 133.6s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[ 151.9s] run bb635a75-92bc-4db1-b56e-eed2d291421d → completed after 16s
[ 151.9s] run bb635a75-92bc-4db1-b56e-eed2d291421d → completed after 0s
[ 153.1s] agentic run → completed; answer: 42; steps: route::completed tool_call:sitefiles_add:completed aggregate::completed
[ 153.3s] shot 12-bypass-agentic-run.png
[ 158.7s] redis: mode=redis tools:g6/29 skills:g8/7 sub_agents:g9/5 settings:g21/110
[ 158.9s] shot 13-cache-redis-status.png
[ 159.0s] settings ← {"registry_cache_mode":"memory","orchestrator_mode":"graph"}
[ 159.0s] restored registry_cache_mode=memory
[ 159.0s] # end — 2026-09-10T18:20:58.153Z
```
