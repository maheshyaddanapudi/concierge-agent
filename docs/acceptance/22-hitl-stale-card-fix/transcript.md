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
> This stage's exact claim — a gate resolved on one surface collapsing on the other — is what `ChatPage.tsx`'s new event fold was written to guarantee ("never leave armed buttons on a dead gate"). The behaviour is probably still true; the implementation under the frames is not the one photographed.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 22-hitl-stale-card-fix — 2026-09-10T03:22:54.770Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null}
[   2.2s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  27.9s] shot 00-gate-armed-in-chat.png
[  30.2s] shot 03-queue-pending-second-tab.png (second tab)
[  30.2s] approved from the queue tab
[  32.7s] chat card after the cross-surface approval: collapsed
[  32.9s] shot 01-card-collapsed-cross-surface.png
[  59.3s] run 335cea92-ad49-4cf0-8e92-b3e66fd3045c → completed after 26s
[  61.0s] shot 02-run-completed.png
[  61.0s] leg A run → completed; steps: plan::completed route::completed skill:s1:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed tool_call:sitefiles_echo:completed tool_call:sitefiles_add:completed hitl:approve:completed skill:finish:completed route:route:approve:completed route:route:finish:completed aggregate::completed
[  61.4s] UI send: Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 m
[  87.2s] shot 04-direct-approve-collapsed.png
[  87.2s] hitl pending: 1 → 0 after the direct approve
[  89.4s] shot 05-queue-resolved-second-tab.png (second tab)
[ 114.8s] run 72d7f0fa-ce5a-46b0-9f1d-dd9dc70e4ec7 → completed after 25s
[ 114.8s] leg B run → completed
[ 114.8s] # end — 2026-09-10T03:24:49.558Z
```
