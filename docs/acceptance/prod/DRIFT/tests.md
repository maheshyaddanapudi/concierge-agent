# Backend test suite on the schema-drift commit — 2026-09-11T00:55:10Z — fake provider, test db pgvector 0.8.6-pg16, provider key and redis URL unset

The suite after the schema-drift, pinned-registry and overlap-judge-model changes: fifteen new tests in `tests/test_schema_drift.py` (the fingerprint, the write rule under warn and quarantine, a live stub server renaming a parameter and the acknowledgement through the API, the settings, and the version pinned into direct-tool, skill-loop and agentic runs and their snapshots) plus the existing suite.

```

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1092 passed, 1 skipped, 1 warning in 336.12s (0:05:36)
```
