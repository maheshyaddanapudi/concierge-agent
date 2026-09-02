# M51 contract tests — 29 passed

`pytest tests/test_m51_bounded.py -v` on the fake provider. Of note for §14n-76: the three strict-session tests (memory write, run digest, ambient drain) pass because the fake provider refuses any model or embedding call made while the calling task holds a database session open.

```text
============================= test session starts ==============================
collecting ... collected 29 items

tests/test_m51_bounded.py::test_port_limits_come_from_env PASSED         [  3%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[anthropic] PASSED [  6%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[custom] PASSED [ 10%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[fake] PASSED [ 13%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[google_genai] PASSED [ 17%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[openai] PASSED [ 20%]
tests/test_m51_bounded.py::test_every_adapter_honors_the_port_limits[openrouter] PASSED [ 24%]
tests/test_m51_bounded.py::test_provider_errors_are_classified PASSED    [ 27%]
tests/test_m51_bounded.py::test_retired_model_is_refused_at_validation PASSED [ 31%]
tests/test_m51_bounded.py::test_provider_failure_names_the_setting_it_came_from[asyncio] PASSED [ 34%]
tests/test_m51_bounded.py::test_run_wall_clock_terminates_with_a_truthful_status[asyncio] PASSED [ 37%]
tests/test_m51_bounded.py::test_every_run_heartbeats_while_it_executes[asyncio] PASSED [ 41%]
tests/test_m51_bounded.py::test_stalled_reaper_covers_chat_runs_too[asyncio] PASSED [ 44%]
tests/test_m51_bounded.py::test_admission_bounds_concurrency_and_sheds_load[asyncio] PASSED [ 48%]
tests/test_m51_bounded.py::test_orphaned_runs_are_reaped_at_startup[asyncio] PASSED [ 51%]
tests/test_m51_bounded.py::test_shutdown_drain_waits_then_cancels[asyncio] PASSED [ 55%]
tests/test_m51_bounded.py::test_readiness_gates_admission[asyncio] PASSED [ 58%]
tests/test_m51_bounded.py::test_session_tracker_counts_open_sessions[asyncio] PASSED [ 62%]
tests/test_m51_bounded.py::test_memory_write_never_holds_a_session_across_the_embedding_call[asyncio] PASSED [ 65%]
tests/test_m51_bounded.py::test_digest_never_holds_a_session_across_the_model_call[asyncio] PASSED [ 68%]
tests/test_m51_bounded.py::test_drain_claims_then_commits_then_processes[asyncio] PASSED [ 72%]
tests/test_m51_bounded.py::test_external_send_retries_with_backoff_then_dead_letters[asyncio] PASSED [ 75%]
tests/test_m51_bounded.py::test_flush_dispatches_before_it_commits[asyncio] PASSED [ 79%]
tests/test_m51_bounded.py::test_registry_cache_fails_open_to_postgres[asyncio] PASSED [ 82%]
tests/test_m51_bounded.py::test_token_totals_increment_atomically[asyncio] PASSED [ 86%]
tests/test_m51_bounded.py::test_contradiction_sweep_keeps_the_newest_fact[asyncio] PASSED [ 89%]
tests/test_m51_bounded.py::test_run_wall_clock_setting_is_validated PASSED [ 93%]
tests/test_m51_bounded.py::test_event_bus_is_bounded_and_read_paths_create_nothing PASSED [ 96%]
tests/test_m51_bounded.py::test_start_run_task_signature_is_admission_aware PASSED [100%]

============================= 29 passed in 10.43s ==============================
```
