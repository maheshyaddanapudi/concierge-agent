<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `ab07205`** (the third-reading build) — **2 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: C — the hardening wave moved what this page claims**
> `hardening-wave.md` was captured on the round-two build and `third-reading.md` on the third-reading build. Both predate the wave, which changed the pinned-snapshot contents these drills read back — HEAD ships 27 prompt files where these pages record 24.
>
> Full build attribution, per-drill grading and the audited counts:
> [`../../STALENESS.md`](../../STALENESS.md)

# Frontend lint and test run on the third-reading follow-up — 2026-09-12T15:02Z

Ten tests in `src/test/hardening-wave.test.tsx`: every pinned record collected from the catalog and the per-entry snapshots once; the same / changed / deleted / inactive comparison with a rename named; the trace showing the entity names the route steps pinned (a worker node's skill never becomes a "sub agent" chip), the format step, the definition version on a route step, the moved count, the prices the run was costed with, the settings and the list-shaped injected context on demand; the Skills list badging only the skill whose bound tool is quarantined, with the reason classification for deleted, quarantined, missing, inactive and (third reading) `remote agent disabled` for an A2A tool taken out with its agent; Settings with the registry overlap audit gate patching the setting, the eval judge model select inheriting the default, and the salience hint when the judge inherits the answering model; and (third reading, named by a reader) a skill save whose overlap check comes back `judge_available: false` going through with a dismissible "Saved unjudged" notice carrying the judge's error, and staying silent when the judge ran.

```
$ cd frontend && npm run lint && npm run test
✖ 20 problems (0 errors, 20 warnings)
 Test Files  13 passed (13)
      Tests  109 passed (109)
```
