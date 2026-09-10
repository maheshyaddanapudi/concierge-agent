# Live sample — openrouter:qwen/qwen3.8-max under the bounded machinery

An ordinary chat run on the real model after every M51 bound is in place: admitted, executed with a 30 s heartbeat (`last_heartbeat_at` advanced at +30 s of a 38 s run), completed with the answer and the token totals. Captured by `m51-live.sh`.

```text

$ backend env: the port limits and the drain window
LLM_TIMEOUT_S= LLM_MAX_RETRIES= SHUTDOWN_GRACE_S= (empty = code defaults 120 / 2 / 25)

$ PATCH /settings default_model=openrouter:qwen/qwen3.8-max, formatter on, graph mode, defaults for admission
{'default_model': 'openrouter:qwen/qwen3.8-max', 'run_max_concurrent': 8, 'run_queue_max': 32, 'run_wall_clock_s': 900}

$ GET /ready
{"status": "ready", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0}

$ POST /chat (live) and sample the status every 250 ms
run_id=0e01a612-c757-4c2e-b987-d5a3d6d2ea36
  t= 0.25s  running
  t=35.00s  completed

$ GET /runs/0e01a612-c757-4c2e-b987-d5a3d6d2ea36
{'status': 'completed', 'orchestrator_mode': 'graph', 'total_input_tokens': 4227, 'total_output_tokens': 1663, 'error': None}
--- final_answer ---
- **Time out and retry with fallback**: set strict timeouts, retry with exponential backoff + jitter, and automatically fail over to a secondary provider or redundant model when one hangs or is unhealthy (circuit breaker to avoid hammering it).
- **Respect and manage rate limits**: track quotas, queue or throttle requests, honor retry-after/429 signals, and spread load across keys/regions/providers so bursts degrade gracefully instead of failing.
- **Abstract and version models**: keep provider calls behind an adapter/interface with pinned model versions, monitor deprecation notices, and maintain tested fallback mappings so a retired model can be swapped without code changes.

$ psql: heartbeat and lifetime
completed|00:13:37|00:14:07|00:14:15|38.4

$ steps and their models
[('plan', 'openrouter:qwen/qwen3.8-max', 'completed')]

$ GET /ready after
{"status": "ready", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 8}
```
