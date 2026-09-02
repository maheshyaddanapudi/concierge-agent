# §14n-70/71 — a hung provider ends at the wall clock; a 429 is named and counted

Fake-provider fault injection on the shipped stack (`FAKE_LLM_ENABLED=1`, the same scriptable provider the test suite uses): one answer scripted to arrive after 300 s, then one scripted 429. Captured by `m51-fault2.sh` against the rebuilt image.

```text

$ PATCH /settings run_wall_clock_s=10 → 422 (floor is 30)
{"detail":"run_wall_clock_s must be an integer between 30 and 86400 seconds"}
HTTP 422

$ PATCH /settings default_model=fake:scripted, formatter off, run_wall_clock_s=45
{'default_model': 'fake:scripted', 'run_wall_clock_s': 45, 'run_max_concurrent': 8, 'run_queue_max': 32}

$ POST /_fake/script — the next provider answer takes 300 s to arrive (a hung provider)
{"queued":1,"pending":1}

$ POST /chat
run_id=a5d40078-0fd4-48ad-99ce-ec8cb57da09e
→ failed after 45s
wall time: 45s

$ GET /runs/a5d40078-0fd4-48ad-99ce-ec8cb57da09e
{'status': 'failed', 'error': 'exceeded the run wall clock (45s, run_wall_clock_s) — terminated', 'started_at': '2026-09-02T00:07:06.002799+00:00', 'finished_at': '2026-09-02T00:07:51.050414+00:00'}

$ psql: the heartbeat advanced while it ran (30 s cadence), the clock ended it at 45 s
failed|00:07:06|00:07:36|00:07:51|45

$ psql: no step left running
plan|cancelled

$ GET /metrics runs_total{status=failed}
concierge_runs_total{mode="graph",status="failed"} 1.0

$ GET /metrics llm_errors (before)
(none yet)

$ POST /_fake/script — the provider answers 429
{"queued":1,"pending":1}

$ POST /chat
run_id=ad46b9c3-3d5d-45e8-b175-29b1fec370ae
→ failed after 2s

$ GET /runs/ad46b9c3-3d5d-45e8-b175-29b1fec370ae — the error names the class, the model, and the setting
{'status': 'failed', 'error': "provider rate-limited (429) after the port's retry budget — RuntimeError: 429 Too Many Requests: rate limit exceeded, retry after 20s (model settings in play: default_model=fake:scripted, embedding_model=openai:text-embedding-3-small)"}

$ GET /metrics llm_errors (after)
concierge_llm_errors_total{kind="rate_limited"} 1.0

$ PATCH /settings default_model=openrouter:qwen/no-such-model → 422 (unknown model refused at validation)
{"detail":"default_model: model 'qwen/no-such-model' is not in provider 'openrouter''s model list"}
HTTP 422
```
