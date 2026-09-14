<!-- staleness-banner -->
> ## ⚠ STALE EVIDENCE — this page predates the current code
>
> **Captured on build `b624908`** (release 1.0.0 / M1–M56 — the campaign build) — **6 source commits behind HEAD `3891914`.**
> It does **not** show the code as it stands. The hardening wave (`401914a`,
> ~470 findings across 220 files) landed afterwards and the planned live
> re-run of this tree **never happened** — the provider account ran out of
> credit and Docker was lost, so no stack could be built or run.
> Nothing on this page has been re-verified.
>
> **Staleness grade: C — the hardening wave moved what this page claims**
> The load baseline was measured before `limits.py` existed: the inbound rate limiter used to sit behind auth, which ships dark, so this run never met it. On HEAD the limiter is unconditional and the harness has to raise its keys for the duration of a run.
>
> Full build attribution, per-drill grading and the audited counts:
> [`../../STALENESS.md`](../../STALENESS.md)

# Load baseline — ambient-burst

Captured 2026-09-10T21:30:41+00:00 at commit `8d5424c` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 14.

## Ambient backlog

Fired 40 webhook events: codes {'202': 40}, fire p95 409.07 ms.
Drain of 40 accepted events: 63.11 s (0.63 events/s); verdicts {'fired': 40}.
Runs: {'completed': 40}, all terminal after 66.12 s; peak connections 24.

