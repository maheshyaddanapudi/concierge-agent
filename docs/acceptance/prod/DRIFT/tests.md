<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `58f77e7`** (the schema-drift build) — **4 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: B — the surface moved underneath; the claim still stands**
> The drift rule itself barely moved in the wave (`toolschema.py` +4). Captured two builds before the wave nonetheless.
>
> Full build attribution, per-drill grading and the audited counts:
> [`../../STALENESS.md`](../../STALENESS.md)

# Backend test suite on the schema-drift commit — 2026-09-11T00:55:10Z — fake provider, test db pgvector 0.8.6-pg16, provider key and redis URL unset

The suite after the schema-drift, pinned-registry and overlap-judge-model changes: fifteen new tests in `tests/test_schema_drift.py` (the fingerprint, the write rule under warn and quarantine, a live stub server renaming a parameter and the acknowledgement through the API, the settings, and the version pinned into direct-tool, skill-loop and agentic runs and their snapshots) plus the existing suite.

```

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1092 passed, 1 skipped, 1 warning in 336.12s (0:05:36)
```
