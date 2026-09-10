# M55 — the suites, executed

All on the fake provider (`FAKE_LLM_ENABLED=1`), deterministic and key-free (spec §11); the live-model proof is `seam-drill.md` next to this file.

## `pytest tests/test_m55_seam.py -v` — the seam suite (28): the contract over `builtin` and `stub`, the registry, the stub end-to-end, the structural guard, byte-identity

```
tests/test_m55_seam.py::test_port_shape[stub] PASSED
tests/test_m55_seam.py::test_port_shape[builtin] PASSED
tests/test_m55_seam.py::test_anonymous_principal_is_never_an_owner[stub] PASSED
tests/test_m55_seam.py::test_anonymous_principal_is_never_an_owner[builtin] PASSED
tests/test_m55_seam.py::test_visibility_is_consistent_between_filter_and_row_check[stub] PASSED
tests/test_m55_seam.py::test_visibility_is_consistent_between_filter_and_row_check[builtin] PASSED
tests/test_m55_seam.py::test_memory_visibility_is_a_fragment_over_the_m_alias[stub] PASSED
tests/test_m55_seam.py::test_memory_visibility_is_a_fragment_over_the_m_alias[builtin] PASSED
tests/test_m55_seam.py::test_reads_are_never_refused_by_authorize[stub] PASSED
tests/test_m55_seam.py::test_reads_are_never_refused_by_authorize[builtin] PASSED
tests/test_m55_seam.py::test_authorize_returns_a_reason_string_or_none[stub] PASSED
tests/test_m55_seam.py::test_authorize_returns_a_reason_string_or_none[builtin] PASSED
tests/test_m55_seam.py::test_on_boot_is_idempotent[stub] PASSED
tests/test_m55_seam.py::test_on_boot_is_idempotent[builtin] PASSED
tests/test_m55_seam.py::TestRegistry::test_builtin_is_the_default_and_the_stub_is_registered PASSED
tests/test_m55_seam.py::TestRegistry::test_unknown_provider_is_refused_at_resolution PASSED
tests/test_m55_seam.py::TestRegistry::test_a_provider_module_is_imported_on_demand PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_rows_are_shared_by_tenant_and_invisible_across PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_memory_recall_follows_the_stub_rule PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_writes_need_the_editor_role_and_reads_do_not PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_no_identity_is_401_and_exempt_paths_stay_open PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_the_builtin_login_is_not_offered_by_another_provider PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_run_ownership_follows_the_provider PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_streams_ask_the_port_too PASSED
tests/test_m55_seam.py::TestStubEndToEnd::test_ambient_stream_delivers_only_what_the_port_admits PASSED
tests/test_m55_seam.py::TestSeamIsReal::test_no_call_site_outside_the_package_reads_the_auth_switch PASSED
tests/test_m55_seam.py::TestSeamIsReal::test_the_stub_lives_in_one_module PASSED
tests/test_m55_seam.py::TestSeamIsReal::test_default_provider_is_byte_identical_single_user PASSED
============================== 28 passed in 5.73s ==============================
```

## `pytest` — the whole backend suite with the seam in place (§14r-98: the default provider is byte-identical)

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1068 passed, 1 skipped, 1 warning in 347.34s (0:05:47)
```

## Static gates

```
$ ruff check . && ruff format --check .
All checks passed!
$ mypy app
Success: no issues found in 148 source files
$ python -m app.doclint
doclint: 5 skill file(s), 1 agent file(s) — 0 error(s), 0 warning(s)
$ python -m app.prompts.check
prompt golden sets: 24 prompts, 24 cases, 0 failed
```

The frontend did not change in M55; its gates (lint 0 errors, 94 tests, build) are recorded in `../M54/tests.md`.
