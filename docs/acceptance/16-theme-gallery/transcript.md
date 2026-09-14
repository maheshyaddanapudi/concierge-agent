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
> **Staleness grade: B — the surface moved underneath; the claim still stands**
> `theme.ts` changed only to guard `localStorage` against a browser that throws on it. No palette value moved, and the four palettes are CSS the wave did not touch. The answer text inside the frames would differ on a re-run because the prompts changed, but this stage's claim is about the palettes and it still holds.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 16-theme-gallery — 2026-09-10T03:24:49.559Z
[   0.0s] answer used for the gallery: run 72d7f0fa-ce5a-46b0-9f1d-dd9dc70e4ec7 (structured artifact present)
[   3.6s] shot theme-default.png
[   7.4s] shot answer-theme-default.png
[   7.4s] theme default: html[data-theme]=null localStorage=default
[  10.8s] shot theme-anthropic.png
[  14.5s] shot answer-theme-anthropic.png
[  14.5s] theme anthropic: html[data-theme]=anthropic localStorage=anthropic
[  18.0s] shot theme-openai.png
[  21.7s] shot answer-theme-openai.png
[  21.7s] theme openai: html[data-theme]=openai localStorage=openai
[  25.1s] shot theme-google.png
[  28.9s] shot answer-theme-google.png
[  28.9s] theme google: html[data-theme]=google localStorage=google
[  32.3s] shot picker-restored-default.png
[  32.3s] # end — 2026-09-10T03:25:21.899Z
```
