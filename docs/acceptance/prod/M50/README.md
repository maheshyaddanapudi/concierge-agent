# M50 — the ceiling: executed proof

The M49 baseline named four ways a fresh install falls over first. M50 fixed
each at its cause; this directory is the same harness and the same stack
(rebuilt image, fresh migration) measured again, plus the two behaviors that
needed screenshots.

| file | what it is |
|---|---|
| `after-runs.json` / `after-runs.md` | The clean 1k → 10k run-table growth record (the `after` run had inherited the 10k table from the screenshot seed, so it measured both levels at 10k) |
| `after.json` / `after.md` | The load harness re-run for the scenarios M50 changed — `sse` (60 streams attempted on a HITL-paused run) and `runs-scale` (`/runs` and `/conversations` at 1k and 10k runs) — same command, same fake provider, same machine as the M49 baseline |
| `quarantine.md` | §14m-68 transcript: four malformed triggers refused with 422 at the API, then a `once.at` corrupted past the API beside a healthy routine — the healthy one fires, the broken one reaches `status='error'` after three ticks, the evaluator-error counter moves, the tick keeps ticking |
| `01-runs-page-paged-under-load.png` | The Runs page over a 10k-run table: a 100-row page with "Show more", not a 9.5 MB list |
| `02-ambient-routines-quarantined.png` | The Ambient page showing the quarantined routine (status `error`, reason on hover) beside the healthy one |
| `03-settings-ambient-timezone.png` | The Ambient section of Settings with `ambient_timezone` beside the quiet hours it governs |
| `timezone.md` | §14m-69 transcript: the setting validated (422 for an unknown zone), and `in_quiet_hours` evaluated for the same instant in UTC and Europe/Lisbon |

## Before → after

| measure | M49 baseline | M50 after |
|---|---|---|
| `/chat/stream` subscribers with a healthy probe | 10 (probe failed at 15; 21 connections at the failure step) | **60** of 60 attempted, every probe 3/3, connections flat at 13 |
| `/runs` at ~1k runs (p50 / p95 / payload) | 348.28 ms / 406.12 ms / 945 KB | **6.95 ms / 9.01 ms / 47 KB** |
| `/runs` at ~10k runs (p50 / p95 / payload) | 2190.61 ms / 2563.07 ms / 9468 KB | **8.08 ms / 10.03 ms / 47 KB** — flat across the 10× growth |
| `/conversations` at ~1k → ~10k runs (p50) | 343.98 → 2392.78 ms | **6.01 → 8.3 ms** (run_count is an aggregate) |
| Malformed trigger in the routine table | raised out of `evaluate_schedules`; no routine after it evaluated | **quarantined** (`status='error'` after 3, reason recorded), healthy routine fires, counter increments — `quarantine.md` |
| Quiet hours for a user off UTC | evaluated in UTC | **wall-clock in `ambient_timezone`** — `timezone.md` |

## Reproduce

```bash
FAKE_LLM_ENABLED=1 docker compose up -d --build      # plus a db port mapping (5555:5432)
cd backend
.venv/bin/python ../experiments/load/harness.py --scenarios sse,runs-scale --sse-max 60 \
    --label m50-after --out ../docs/acceptance/prod/M50/after.json
pytest tests/test_m50_ceiling.py -q
```
