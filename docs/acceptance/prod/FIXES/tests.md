# Backend test suite on the fix commit — 2026-09-10T23:42:27Z — fake provider, test db pgvector 0.8.6-pg16, provider key and redis URL unset

The suite after the campaign v1 fixes (CHANGELOG "Fixes from campaign v1"): the eight new regression tests (four for the ambient dark tick and the loop that survives it, two for the worker result, two for the formatter's prose retry; the deny test gained its aggregator assertions and the aggregator golden set a denied-gate case) plus the existing suite.

```
  /usr/lib/python3.12/contextlib.py:105: DeprecationWarning: Use `streamable_http_client` instead.
    self.gen = func(*args, **kwds)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1077 passed, 1 skipped, 1 warning in 313.95s (0:05:13)
```
