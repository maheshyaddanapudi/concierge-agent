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
> `00-purged-settings.png` shows the retention block, which the wave took from six tables to nine and gave six new settings keys; `retention.py` moved +195/−13.
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 17-data-purge — 2026-09-10T03:03:13.782Z
[   1.5s] runs before purge: 16
[   1.7s] shot 02-runs-before-purge.png
[   3.3s] confirm dialog: Purge ALL run history? This cannot be undone.
[   5.8s] runs after purge: 0; conversations: 11
[   6.0s] shot 00-purged-settings.png
[   7.7s] shot 01-runs-empty-after-purge.png
[   9.7s] UI send: Add 40 and 2 with the sitefiles add tool and answer with the number only.
[  56.7s] run 0c41fc97-cefb-45bb-a01b-e6bb9247cff7 → completed after 0s
[  58.4s] shot 04-post-purge-clean-run.png
[  58.4s] post-purge run → completed; answer: 42

(Note: no "sitefiles add" tool is available in this system — only `sitefiles.echo` — so I computed the sum directly.; steps: plan::completed
[  58.4s] # end — 2026-09-10T03:04:12.147Z
```
