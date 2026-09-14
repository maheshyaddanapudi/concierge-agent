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
> **Staleness grade: B — the surface moved underneath; the claim still stands**
> `McpServersPage.tsx` was not touched and the stdio registration this stage drives still succeeds — its `python` launcher is on the wave's new allowlist. What moved around it: operator-disable intent (`disabled_at`) and the launcher guard extended to PATCH.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 02-mcp-servers — 2026-09-11T22:35:01.369Z
[   1.9s] shot 00-servers-page.png
[   2.7s] shot 01-register-form.png
[   6.8s] registered: sitefiles active tools=5 transport=stdio
[   6.9s] shot 02-sitefiles-active.png
[   7.6s] shot 03-register-form-http.png
[   9.0s] shot 04-server-drawer-detail.png
[   9.3s] shot 05-refresh-tools-clicked.png
[  15.4s] after reconnect: active tools=5 last_connected=2026-09-11T22:35:13.934850Z
[  15.5s] shot 06-reconnect-done.png
[  15.9s] # end — 2026-09-11T22:35:17.314Z
```
