# M54 — the suites, executed

All on the fake provider (`FAKE_LLM_ENABLED=1`), deterministic and key-free (spec §11); the live-model proofs are the transcripts next to this file.

## `pytest tests/test_m54_scale.py -v` — the M54 contract suite (39)

```
tests/test_m54_scale.py::TestReplicaIdentity::test_identity_is_stable_and_env_overridable PASSED
tests/test_m54_scale.py::TestReplicaIdentity::test_heartbeat_row_and_liveness[asyncio] PASSED
tests/test_m54_scale.py::TestReplicaIdentity::test_replicas_endpoint_lists_the_fleet_and_the_budget[asyncio] PASSED
tests/test_m54_scale.py::TestReplicaIdentity::test_retire_removes_the_row[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_created_run_is_owned_by_this_replica[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_local_cancel_still_cancels_the_task[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_foreign_cancel_is_an_intent_not_a_lie[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_foreign_cancel_reports_cancelled_once_the_owner_acts[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_cancel_api_reports_the_real_status[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_owner_observes_the_intent_from_the_control_channel[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_owner_observes_the_intent_from_its_heartbeat[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_boot_reap_is_scoped_to_this_replica[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_dead_owner_runs_are_reaped_truthfully[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_terminal_transitions_are_announced[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_foreign_stream_resolves_when_the_owner_announces[asyncio] PASSED
tests/test_m54_scale.py::TestRunOwnership::test_foreign_stream_falls_back_to_the_row_at_each_beat[asyncio] PASSED
tests/test_m54_scale.py::TestJobClock::test_due_then_ran_then_not_due_until_the_interval[asyncio] PASSED
tests/test_m54_scale.py::TestJobClock::test_consolidation_runs_once_per_interval_across_processes[asyncio] PASSED
tests/test_m54_scale.py::TestJobClock::test_retention_keeps_the_same_clock[asyncio] PASSED
tests/test_m54_scale.py::TestJobClock::test_boot_lock_is_a_session_advisory_lock[asyncio] PASSED
tests/test_m54_scale.py::TestDeliveryFanOut::test_publish_announces_and_fan_in_reaches_local_subscribers[asyncio] PASSED
tests/test_m54_scale.py::TestDeliveryFanOut::test_pursuit_uses_the_cluster_audience[asyncio] PASSED
tests/test_m54_scale.py::TestDistributedRateLimiter::test_one_bucket_for_every_replica[asyncio] PASSED
tests/test_m54_scale.py::TestDistributedRateLimiter::test_idle_keys_are_evicted[asyncio] PASSED
tests/test_m54_scale.py::TestCacheCoherency::test_a_dirty_mark_during_a_reload_is_not_lost[asyncio] PASSED
tests/test_m54_scale.py::TestCacheCoherency::test_memory_entries_expire_on_the_ttl[asyncio] PASSED
tests/test_m54_scale.py::TestMcpUnderReplicas::test_concurrent_ingest_is_idempotent[asyncio] PASSED
tests/test_m54_scale.py::TestMcpUnderReplicas::test_each_replica_reconciles_its_subprocess_set[asyncio] PASSED
tests/test_m54_scale.py::TestTypedEmbeddings::test_write_lands_in_the_typed_column_with_an_hnsw_index[asyncio] PASSED
tests/test_m54_scale.py::TestJobsAtScale::test_decay_sweep_is_one_update_over_twenty_thousand_rows[asyncio] PASSED
tests/test_m54_scale.py::TestJobsAtScale::test_contradiction_sweep_is_one_update_over_many_groups[asyncio] PASSED
tests/test_m54_scale.py::TestJobsAtScale::test_memory_self_references_are_indexed[asyncio] PASSED
tests/test_m54_scale.py::TestJobClock::test_lifespan_boots_under_the_lock PASSED
tests/test_m54_scale.py::TestConnectionBudget::test_arithmetic_is_published PASSED
tests/test_m54_scale.py::TestConnectionBudget::test_pooled_connections_survive_a_transaction_pooler PASSED
tests/test_m54_scale.py::TestDistributedRateLimiter::test_middleware_uses_the_shared_bucket_and_the_loop_evicts PASSED
tests/test_m54_scale.py::TestCacheCoherency::test_redis_blob_is_written_with_a_ttl_and_under_the_generation_guard PASSED
tests/test_m54_scale.py::TestTypedEmbeddings::test_column_routing PASSED
tests/test_m54_scale.py::TestTypedEmbeddings::test_every_vector_query_uses_the_typed_column PASSED
============================= 39 passed in 12.36s ==============================
```

## `pytest` — the whole backend suite

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1040 passed, 1 skipped, 1 warning in 302.80s (0:05:02)
```

One test in the full run was timing-flaky under load (`test_circuit_opens_after_the_attempt_budget`, M53) and one reset the wrong limiter store since M54 (`test_rate_limit_429`); both were fixed in this wave and the run above is clean.

## `npm run lint && npm run test -- --run && npm run build` — the frontend

```
✖ 15 problems (0 errors, 15 warnings)
lint exit 0
 Test Files  11 passed (11)
      Tests  94 passed (94)
test exit 0
✓ built in 6.59s
build exit 0
```

## Static gates

```
$ ruff check . && ruff format --check .
All checks passed!
$ mypy app
Success: no issues found in 145 source files
$ python -m app.doclint
doclint: 5 skill file(s), 1 agent file(s) — 0 error(s), 0 warning(s)
$ python -m app.prompts.check
prompt golden sets: 24 prompts, 24 cases, 0 failed
```
