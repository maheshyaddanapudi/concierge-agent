<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `24e53b6`** (the campaign-fixes build (findings 1, 2, 4)) — **5 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: B — the surface moved underneath; the claim still stands**
> The two regressions re-verified here (a HITL deny reported as a refusal, the ambient tick leading again after off→on) were not re-opened by the wave, but `factory/worker.py` and the ambient loop both moved under them.
>
> Full build attribution, per-drill grading and the audited counts:
> [`../../STALENESS.md`](../../STALENESS.md)

# Backend test suite on the fix commit — 2026-09-10T23:42:27Z — fake provider, test db pgvector 0.8.6-pg16, provider key and redis URL unset

The suite after the campaign v1 fixes (CHANGELOG "Fixes from campaign v1"): the eight new regression tests (four for the ambient dark tick and the loop that survives it, two for the worker result, two for the formatter's prose retry; the deny test gained its aggregator assertions and the aggregator golden set a denied-gate case) plus the existing suite.

```
  /usr/lib/python3.12/contextlib.py:105: DeprecationWarning: Use `streamable_http_client` instead.
    self.gen = func(*args, **kwds)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1077 passed, 1 skipped, 1 warning in 313.95s (0:05:13)
```
