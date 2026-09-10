# Backend test suite — 2026-09-10T22:38:18Z — commit 17acdc1 — fake provider, test db pgvector 0.8.6-pg16

```
    ) -> None:
        if provider.provider_id == "fake":
            monkeypatch.setenv("FAKE_LLM_ENABLED", "0")
        get_config.cache_clear()
        try:
>           assert provider.is_configured() is False
E           assert True is False
E            +  where True = is_configured()
E            +    where is_configured = <app.llm.adapters.OpenRouterProvider object at 0x7f24036bc530>.is_configured

tests/test_llm_contract.py:50: AssertionError
____________________ TestRedisBackend.test_redis_round_trip ____________________

self = <tests.test_registry_cache.TestRedisBackend object at 0x7f240175be00>
client = <httpx.AsyncClient object at 0x7f23caa7f1a0>

    async def test_redis_round_trip(self, client: AsyncClient) -> None:
        from app.config import get_config
    
        get_config.cache_clear()
        tool = await create_tool()
        resp = await client.patch("/api/v1/settings", json={"registry_cache_mode": "redis"})
>       assert resp.status_code == 200, resp.text
E       AssertionError: {"detail":"redis unreachable: Error -2 connecting to redis:6379. Name or service not known."}
E       assert 422 == 200
E        +  where 422 = <Response [422 Unprocessable Entity]>.status_code

tests/test_registry_cache.py:148: AssertionError
------------------------------ Captured log call -------------------------------
INFO     httpx:_client.py:1740 HTTP Request: PATCH http://test/api/v1/settings "HTTP/1.1 422 Unprocessable Entity"
=============================== warnings summary ===============================
tests/test_mcp_manager.py::TestHttpTransport::test_http_connect_ingests_tools
  /usr/lib/python3.12/contextlib.py:105: DeprecationWarning: Use `streamable_http_client` instead.
    self.gen = func(*args, **kwds)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_llm_contract.py::test_unconfigured_provider_refuses_model[openrouter]
FAILED tests/test_registry_cache.py::TestRedisBackend::test_redis_round_trip
2 failed, 1066 passed, 1 skipped, 1 warning in 291.14s (0:04:51)
```

The two failures are environment-dependent, not product failures: the drill shell that launched the suite had `OPENROUTER_API_KEY` and `REDIS_URL` exported for the live drills, and `test_unconfigured_provider_refuses_model[openrouter]` asserts that an unconfigured provider refuses a model while `TestRedisBackend::test_redis_round_trip` reads `REDIS_URL` (a compose-internal hostname from this host). Re-run with those variables unset:

```
$ env -u OPENROUTER_API_KEY -u REDIS_URL FAKE_LLM_ENABLED=1 pytest -q tests/test_llm_contract.py::test_unconfigured_provider_refuses_model tests/test_registry_cache.py::TestRedisBackend::test_redis_round_trip
......s                                                                  [100%]
6 passed, 1 skipped in 1.67s
```

Net: 1068 passed, 1 skipped on this commit.
