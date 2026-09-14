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
> Captured before the seed pinned its filesystem MCP package. HEAD launches `@modelcontextprotocol/server-filesystem@2026.8.31`; this capture launched the spec unpinned, so the recorded `filesystem:active/14` and `25 tools` may not reproduce. The registry cache a fresh stack boots with also changed (`bypass` → `memory`).
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 00-fresh-slate — 2026-09-10T02:34:02.422Z
[   0.1s] seed: 2 servers fetch:active/1 filesystem:active/14; 25 tools; skills file-ops, memory-keeper, web-research, workspace-auditor, workspace-curator; sub agents research-concierge, workspace-reporter, workspace-warden
[   0.1s] runs at rest: 0
[   1.9s] shot 00-servers-seeded.png
[   3.7s] shot 01-tools-seeded.png
[   5.4s] shot 02-skills-seeded.png
[   7.1s] shot 03-research-concierge.png
[   8.8s] shot 04-runs-empty.png
[  10.5s] shot 05-chat-home-empty.png
[  10.5s] # end — 2026-09-10T02:34:12.889Z
```
