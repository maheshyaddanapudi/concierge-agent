# Backend test suite on the hardening-wave commit — 2026-09-11T21:10Z — fake provider, test db pgvector 0.8.6-pg16, provider key and redis URL unset

The suite after the hardening wave and its second reading: `tests/test_hardening_wave.py` (sixty tests over the three frames — description fingerprints and the operator's wording under a live stub re-ingest, `tool_key` rename guards, the MCP config hash and the reconnect on edit and on a secret rotation, A2A card versions and the disabled agent that a refresh never re-enables, bind-time collisions and unavailable bound tools with their reasons, the hallucinated name handed back, an inactive workflow skill on the error edge, stale vectors ignored and self-healed, the backfill on an embedding-model change, definition versions through the API and the seed, entity names / versions / model params on steps including route, plan and aggregate, the settings / prompts / context / catalog-slice snapshot on routed and agentic runs, the format step counted once, the cost stamped and unmoved by a price change, the ambient lineage and the pinned allowlist, delivery policy ids, the eval snapshot with its judge, mining through lint and a judge that must be available, activation judged again by origin, the deferred and harvested exemplar votes with every pending run settled, inferred memories quarantined, the citation cap, the overlap audit on its own clock with or without the memory layer, the watch predicate), plus the procedural tests updated for pending harvests and the judged mining path.

```
$ cd backend && env -u OPENROUTER_API_KEY -u REDIS_URL FAKE_LLM_ENABLED=1 TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/concierge_test .venv/bin/pytest -q -p no:cacheprovider

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1152 passed, 1 skipped, 1 warning in 353.33s (0:05:53)
```

Static gates on the same tree: `ruff check` and `ruff format --check` clean, `mypy app` — Success: no issues found in 150 source files.
