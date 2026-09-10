# M52 contract tests — 40 passed

`pytest tests/test_m52_untrusted.py -v` on the fake provider: one adversarial test per untrusted source (fence escape across nine prompts, SSRF by literal and by resolution, a redirect into loopback, the streamed body cap, billion-laughs XML, write-only MCP secrets, the sanitizer on values and shapes, the run path and the connect paths, the regex guard and its timeout).

```text
============================= test session starts ==============================
collecting ... collected 40 items

tests/test_m52_untrusted.py::test_fence_tokens_are_fresh_and_unguessable PASSED [  2%]
tests/test_m52_untrusted.py::test_neutralize_escapes_every_fence_shaped_tag PASSED [  5%]
tests/test_m52_untrusted.py::test_fence_body_clips_and_marks_empty PASSED [  7%]
tests/test_m52_untrusted.py::test_a2a_remote_output_fence_is_unforgeable PASSED [ 10%]
tests/test_m52_untrusted.py::test_delivery_salience_fence_is_unforgeable PASSED [ 12%]
tests/test_m52_untrusted.py::test_ambient_fire_prompts_fence_the_payload PASSED [ 15%]
tests/test_m52_untrusted.py::test_judge_summary_compile_and_significance_prompts_are_fenced PASSED [ 17%]
tests/test_m52_untrusted.py::test_every_fenced_prompt_goes_through_the_one_choke_point PASSED [ 20%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://127.0.0.1/x] PASSED [ 22%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://10.1.2.3/] PASSED [ 25%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://169.254.169.254/latest/meta-data/] PASSED [ 27%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://[::1]/] PASSED [ 30%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://0.0.0.0/] PASSED [ 32%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://192.168.1.1/] PASSED [ 35%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://172.16.0.1/] PASSED [ 37%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://localhost/] PASSED [ 40%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://api.localhost/] PASSED [ 42%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-http://[fd00:ec2::254]/] PASSED [ 45%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-ftp://example.com/x] PASSED [ 47%]
tests/test_m52_untrusted.py::test_private_targets_are_denied_before_any_connection[asyncio-file:///etc/passwd] PASSED [ 50%]
tests/test_m52_untrusted.py::test_a_name_resolving_to_a_private_range_is_denied[asyncio] PASSED [ 52%]
tests/test_m52_untrusted.py::test_redirect_hops_are_rechecked[asyncio] PASSED [ 55%]
tests/test_m52_untrusted.py::test_body_cap_is_enforced_while_streaming[asyncio] PASSED [ 57%]
tests/test_m52_untrusted.py::test_allowlist_and_open_modes[asyncio] PASSED [ 60%]
tests/test_m52_untrusted.py::test_transport_failures_take_the_fixed_shape[asyncio] PASSED [ 62%]
tests/test_m52_untrusted.py::test_poll_sources_and_registries_are_under_the_policy[asyncio] PASSED [ 65%]
tests/test_m52_untrusted.py::test_billion_laughs_feed_is_refused_not_expanded[asyncio] PASSED [ 67%]
tests/test_m52_untrusted.py::test_feed_parse_runs_off_the_event_loop[asyncio] PASSED [ 70%]
tests/test_m52_untrusted.py::test_oversized_feed_is_capped_during_download[asyncio] PASSED [ 72%]
tests/test_m52_untrusted.py::test_mcp_env_and_headers_are_write_only[asyncio] PASSED [ 75%]
tests/test_m52_untrusted.py::test_run_failure_never_persists_a_secret[asyncio] PASSED [ 77%]
tests/test_m52_untrusted.py::test_api_error_details_are_sanitized[asyncio] PASSED [ 80%]
tests/test_m52_untrusted.py::test_regex_filter_is_refused_at_the_api[asyncio] PASSED [ 82%]
tests/test_m52_untrusted.py::test_env_indirection_resolves_at_connect_time PASSED [ 85%]
tests/test_m52_untrusted.py::test_sanitizer_redacts_values_and_shapes PASSED [ 87%]
tests/test_m52_untrusted.py::test_structlog_processor_redacts_every_string_value PASSED [ 90%]
tests/test_m52_untrusted.py::test_connect_errors_are_sanitized_with_the_records_own_secrets PASSED [ 92%]
tests/test_m52_untrusted.py::test_regex_guard_rejects_catastrophic_shapes PASSED [ 95%]
tests/test_m52_untrusted.py::test_slow_regex_is_bounded_by_the_timeout PASSED [ 97%]
tests/test_m52_untrusted.py::test_match_filters_uses_the_guard PASSED    [100%]

============================== 40 passed in 5.82s ==============================
```
