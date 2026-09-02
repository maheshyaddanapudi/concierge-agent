# §14p-89 — the spend ceiling refuses every kind of run

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ GET /spend (live-model runs so far today; qwen priced from OpenRouter's published price)
{'day': '2026-09-02', 'usd_today': 0.258108, 'runs_today': 217, 'unpriced_tokens': 0, 'by_kind': {'chat': 0.046492, 'ambient': 0.211616}, 'ceiling': {'enabled': False, 'usd_per_day': 10.0, 'remaining': None, 'reached': False}}

$ GET /runs?limit=3 → cost_usd per run
[{'status': 'completed', 'total_input_tokens': 2064, 'total_output_tokens': 1026, 'cost_usd': 0.010284, 'cost_priced': True}, {'status': 'completed', 'total_input_tokens': 2047, 'total_output_tokens': 293, 'cost_usd': 0.005852, 'cost_priced': True}, {'status': 'completed', 'total_input_tokens': 2070, 'total_output_tokens': 648, 'cost_usd': 0.008028, 'cost_priced': True}]

$ PATCH /settings: model_prices override for qwen, ceiling 0.0001 USD/day, gate ON
{'spend_ceiling_enabled': True, 'spend_ceiling_usd_per_day': 0.0001, 'model_prices': {'openrouter:qwen/qwen3.8-max': {'input_per_m': 1.0, 'output_per_m': 3.0}}}

$ GET /spend → reached
{'usd_today': 0.129054, 'runs_today': 217, 'by_kind': {'chat': 0.023246, 'ambient': 0.105808}, 'ceiling': {'enabled': True, 'usd_per_day': 0.0001, 'remaining': 0.0, 'reached': True}}

$ POST /chat → 429 + Retry-After
HTTP/1.1 429 Too Many Requests
retry-after: 3600
{"detail":"spend ceiling reached: $0.1291 of $0.00 spent today (spend_ceiling_usd_per_day) — runs of every kind are refused until the UTC day rolls over or the ceiling is raised in Settings → Cost"}

$ ambient: POST /routines (webhook trigger) → token → fire → the drain HOLDS the fire on the event
{'status': 'accepted', 'event_id': '10fb0f9a-d4d2-466c-8356-8a0ae1c22257'}
t+5s: held | spend ceiling: spend ceiling reached: $0.1291 of $0.00 spent today (spend_ceiling_usd_per_day) — runs of every kind are refused until the UTC day rolls over or the ceiling is raised in Settings → Cost

$ psql: the event
held|spend ceiling: spend ceiling reached: $0.1291 of $0.00 spent today (spend_ceiling_usd_per_day) — runs of every kind are 

$ GET /metrics spend series
concierge_spend_usd_today 0.129054
concierge_spend_ceiling_refusals_total{kind="chat"} 1.0
concierge_spend_ceiling_refusals_total{kind="ambient"} 1.0

$ PATCH /settings spend_ceiling_enabled=false → POST /chat 201 (byte-identical admission)
HTTP 200
{"run_id":"35b34be4-c465-40d4-9156-9d46c50a6b87","conversation_id":"36ccc3a6-b1cb-4b3d-9fa5-b96c03828630"} HTTP 201
{'status': 'completed', 'total_input_tokens': 1536, 'total_output_tokens': 128, 'cost_usd': 0.00192, 'cost_priced': True}
cleanup DELETE routine → HTTP 204
```
