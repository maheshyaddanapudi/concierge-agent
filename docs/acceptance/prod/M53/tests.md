# M53 — the suites, executed

All on the fake provider (`FAKE_LLM_ENABLED=1`), deterministic and key-free (spec §11); the live-model proofs are the transcripts next to this file.

## `pytest tests/test_m53_operate.py -v` — the M53 contract suite (44)

```
tests/test_m53_operate.py::TestSseWireFormat::test_bus_assigns_monotonic_seq_and_resumes_after PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_stream_carries_ids_and_last_event_id_resumes[asyncio] PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_terminal_events_are_synthesized_when_history_is_gone[asyncio] PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_heartbeat_is_inside_the_tightest_balancer_default[asyncio] PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_draining_process_closes_streams_it_cannot_serve[asyncio] PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_ambient_stream_carries_ids_and_heartbeats[asyncio] PASSED
tests/test_m53_operate.py::TestSseWireFormat::test_sse_subscriber_gauge_tracks_open_streams[asyncio] PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_begin_drain_flips_readiness_first_and_refuses_runs[asyncio] PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_sigusr1_begins_the_drain[asyncio] PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_ready_reports_the_database_and_degrades_without_it[asyncio] PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_ambient_loop_releases_the_lease_when_cancelled_and_awaited[asyncio] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-ambient_events] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-deliveries] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-ambient_policies] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-pattern_instances] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-a2a_tasks] PASSED
tests/test_m53_operate.py::TestRetention::test_gate_holds_on_direct_calls_and_protected_rows_survive[asyncio-auth_sessions] PASSED
tests/test_m53_operate.py::TestRetention::test_window_keeps_young_rows[asyncio] PASSED
tests/test_m53_operate.py::TestRetention::test_windows_validate[asyncio] PASSED
tests/test_m53_operate.py::TestRetention::test_run_and_preview_surfaces[asyncio] PASSED
tests/test_m53_operate.py::TestRetention::test_retention_runs_under_an_advisory_lock[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_llm_calls_are_measured_at_the_port[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_step_metrics_carry_the_section_10_labels[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_saturation_gauges_are_exported[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_in_flight_gauge_follows_admission[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_backlog_gauges_reflect_pending_rows[asyncio] PASSED
tests/test_m53_operate.py::TestObservability::test_loop_errors_are_counted[asyncio] PASSED
tests/test_m53_operate.py::TestMcpReconnect::test_failed_ping_reconnects_with_backoff[asyncio] PASSED
tests/test_m53_operate.py::TestMcpReconnect::test_circuit_opens_after_the_attempt_budget[asyncio] PASSED
tests/test_m53_operate.py::TestMcpReconnect::test_auto_reconnect_gate_off_means_no_attempts[asyncio] PASSED
tests/test_m53_operate.py::TestMcpReconnect::test_reingest_preserves_operator_intent[asyncio] PASSED
tests/test_m53_operate.py::TestSupervisedListen::test_listener_reconnects_after_its_backend_dies[asyncio] PASSED
tests/test_m53_operate.py::TestSupervisedListen::test_registry_cache_reloads_after_a_listener_gap[asyncio] PASSED
tests/test_m53_operate.py::TestCostModel::test_run_cost_is_computed_from_captured_usage[asyncio] PASSED
tests/test_m53_operate.py::TestCostModel::test_model_prices_validate[asyncio] PASSED
tests/test_m53_operate.py::TestCostModel::test_spend_ceiling_refuses_every_trigger_kind[asyncio] PASSED
tests/test_m53_operate.py::TestCostModel::test_spend_gauge_is_published_by_the_periodic_tick[asyncio] PASSED
tests/test_m53_operate.py::TestCostModel::test_spend_endpoint_breaks_down_by_kind[asyncio] PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_shutdown_awaits_the_loops_it_cancels PASSED
tests/test_m53_operate.py::TestDeployLifecycle::test_deploy_artifacts PASSED
tests/test_m53_operate.py::TestRetention::test_every_unbounded_table_has_its_own_gate_and_window PASSED
tests/test_m53_operate.py::TestRetention::test_destructive_jobs_are_born_dark_except_expired_sessions PASSED
tests/test_m53_operate.py::TestRetention::test_retention_ticks_from_the_periodic_loop PASSED
tests/test_m53_operate.py::TestCostModel::test_price_table_and_cost_math PASSED
============================= 44 passed in 16.03s ==============================
```

## `pytest` — the whole backend suite

```
1001 passed, 1 skipped, 1 warning in 254.26s (0:04:14)
```

## Backend gates

```
== ruff check
All checks passed!
ruff exit 0
== ruff format --check
258 files already formatted
== mypy app
Success: no issues found in 139 source files
== doclint
doclint: 5 skill file(s), 1 agent file(s) — 0 error(s), 0 warning(s)
== prompts.check
prompt golden sets: 24 prompts, 24 cases, 0 failed
```

## Frontend — `npm run lint && npm run test && npm run build`

```
== lint
  401:14  warning  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

✖ 15 problems (0 errors, 15 warnings)

== test
 Test Files  11 passed (11)
      Tests  94 passed (94)
== build
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 4.47s
```

The 15 lint warnings are the pre-existing `react-refresh/only-export-components` notes; 0 errors. The 94 tests include the nine `sse-seq` client tests (idempotent folding, the reconnect hint, the reopen through an HTTP error with `?after=`, the hint delay, the reopen budget, unsubscribe), the M53 Settings sections and the accessibility pass.
