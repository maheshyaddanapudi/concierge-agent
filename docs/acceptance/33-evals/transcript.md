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
> The eval harness no longer auto-approves the human gates it reaches — that is now per-dataset opt-in and every machine-cleared gate is recorded (`evals/runner.py` +107/−10, `api/evals.py` +87/−5, `EvalsPage.tsx`).
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 33-evals — 2026-09-10T20:38:08.026Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"evals_enabled":true,"formatter_enabled":true}
[   0.1s] skill quiz-answerer 6c81d4df-b8fa-4f86-94f7-c83f66f95551
[   2.7s] shot 01-skill-drawer-launcher.png
[   3.9s] launcher → /evals?target=6c81d4df-b8fa-4f86-94f7-c83f66f95551
[   6.0s] dataset: quiz-3 level=skill cases=3
[   6.2s] shot 02-dataset-uploaded.png
[  34.8s] eval run → completed: 3/3 passed, 0 failed, 0 errors
[  34.8s]   exact: pass score=1 — exact match
[  34.8s]   contains: pass score=1 — expected substring present
[  34.8s]   llm_judge: pass score=1 — The answer correctly explains that the atmosphere scatters sunlight and that shorter (blue) wavelengths scatter more tha
[  35.8s] shot 03-graded-results.png
[  35.8s] case runs on the Runs surface: 3 (completed, completed, completed)
[  36.3s] # end — 2026-09-10T20:38:44.299Z
```
