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

# Frontend lint and test run on the schema-drift commit — 2026-09-11T01:00:33Z

Five new tests in `src/test/schema-drift.test.tsx`: the Tools table badge with the new version, the drawer banner and its Acknowledge posting to the API, the re-enable action for a quarantined tool, the Settings policy toggle patching the setting, and the overlap judge's model select inheriting the default.

```
✖ 15 problems (0 errors, 15 warnings)
 Test Files  12 passed (12)
      Tests  99 passed (99)
```
