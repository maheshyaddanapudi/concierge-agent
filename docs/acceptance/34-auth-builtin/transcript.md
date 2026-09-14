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
> `backend/app/auth/` — the provider port, the registry and the builtin provider this stage is about — was NOT touched by the wave. The request pipeline around it was (`api/deps.py` +25, `main.py` +77, and the new `limits.py`).
>
> Full build attribution, per-stage grading and the audited counts:
> [`../STALENESS.md`](../STALENESS.md)

```
[   0.0s] # 34-auth-builtin — 2026-09-10T20:46:03.785Z
[   1.9s] shot 00-login-gate.png
[   3.6s] signed in: token in localStorage=true; me={"id":"f6072205-d49b-44e3-ae92-5a37739dfbe4","username":"admin","role":"admin","prefs":{}}
[   5.3s] shot 01-signed-in-admin.png
[   7.4s] UI send: In one sentence: what does a login gate protect?
[  18.7s] run 719fcbbc-363d-4034-bc65-9acae12e5f94 → completed after 9s
[  18.7s] run 719fcbbc-363d-4034-bc65-9acae12e5f94 → completed after 0s
[  19.9s] run 719fcbbc → completed; steps: plan::completed
[  19.9s] answer: A login gate protects access to whatever lies behind it — an app, account, API, or set of data — by requiring a user to prove their identity (e.g., credentials 
[  19.9s] run under admin: completed
[  20.1s] shot 02-run-under-identity.png
[  23.6s] mallory's Runs page rows: 1 (her own routine run only — admin's run is invisible to her)
[  23.8s] shot 03-member-own-runs-only.png (member context)
[  23.8s] # end — 2026-09-10T20:46:27.564Z
```
