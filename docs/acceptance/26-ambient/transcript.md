```
[   0.0s] # 26-ambient — 2026-09-10T19:11:13.936Z
[   0.1s] settings ← {"orchestrator_mode":"graph","default_model_params":null}
[   3.7s] settings ← {"ambient_quiet_hours":["21:11","21:41"],"ambient_digest_times":["19:14"],"ambient_timezone":"UTC","ambient_salience_mode":"off","ambient_pursuit":"off"}
[   5.3s] ambient_enabled=true tick=15s quiet=["21:11","21:41"] digest_times=["19:14"] channels={}
[   5.9s] shot 00-settings-ambient-section.png
[   5.9s] nav shows Ambient: 1
[   7.6s] shot 01-ambient-inbox-landing.png
[   9.2s] shot 02-routine-builder-webhook-trigger.png
[  10.4s] routine 17e823bf-2af8-4e21-abd9-8840111bafab status=active triggers=[{"type":"webhook","filters":[{"op":"equals","field":"sev","value":"high","values":null}]}]
[  13.1s] fire token issued in the UI: amb_O4Yg… (47 chars, shown once)
[  13.2s] shot 03-routine-fire-token-issued.png
[  13.7s] fire (sev=low, filter says hold) → HTTP 202 {"status":"accepted","event_id":"438209c7-2a7d-4d6e-b5ff-12bd83524760"}
[  13.7s] fire (sev=high) → HTTP 202 {"status":"accepted","event_id":"7ce3c244-55c3-4221-b23c-a46693d20fcc"}
[  13.7s] fire with a wrong token → HTTP 401
[  51.2s] run c0a73e9d-17d4-4fdf-a5b6-7c53d6cba611 → completed after 35s
[  51.2s] routine run c0a73e9d-17d4-4fdf-a5b6-7c53d6cba611 → completed; trigger={"kind":"routine_fire","source":"webhook","urgency":2,"event_id":"7ce3c244-55c3-4221-b23c-a46693d20fcc","intent_id":null,"model_ref":null,"routine_id":"17e823bf-2af8-4e21-abd9-8840111bafab"}; steps: plan::completed
[  51.2s] proposal: **ops-alert-triage run (propose mode, no tools executed)** Two-line summary: - High-severity webhook alert on host `db-01` (service: postgres): replication lag is at 45s and rising. - The primary is r
[  52.9s] shot 04-routine-run-history-live-fire.png
[  54.6s] ledger: routine_fire/fired:  | routine_fire/held:  | routine_fire/fired:  | routine_fire/held: 
[  55.8s] shot 05-ledger-audit-and-chain.png
[  56.3s] shot 06-ledger-precision-panel.png
[  70.3s] shot 07-watch-describe-compiled.png
[  71.5s] watches: active/event: tell me when a high-severity alert appears in the  | active/event: tell me when a high-severity alert appears in the 
[  71.6s] shot 08-watch-confirmed-active.png
[  72.4s] shot 09-watch-typed-filters-proposed.png
[  73.3s] deliveries: 9 delivered — 0/ops/interrupt: probe after off/on | 0/ops/interrupt: probe: tick alive? | 0/ops/interrupt: nightly index rebuild finished
[  75.0s] shot 10-inbox-digest-and-delivered.png
[  77.1s] feedback recorded: accepted reward=0.8
[  77.2s] shot 11-inbox-feedback-recorded.png
[  78.9s] shot 12-evals-page.png
[  78.9s] settings ← {"ambient_quiet_hours":[],"ambient_digest_times":["19:01"],"ambient_tick_interval_s":15}
[  78.9s] quiet hours, digest times and the tick restored
[  78.9s] # end — 2026-09-10T19:12:32.851Z
```
