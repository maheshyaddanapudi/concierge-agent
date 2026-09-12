```
[   0.0s] # 29-ambient-pursuit — 2026-09-10T20:21:56.213Z
[   0.1s] settings ← {"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_quiet_hours":["22:21","22:51"],"ambient_notification_budget_per_day":40,"ambient_salience_mode":"off","ambient_channels":{"interrupt":["in_app","email","webhook"]}}
[   0.1s] # channels={"interrupt":["in_app","email","webhook"]} budget=40 tick=15s
[  12.8s] # preflight: tier-0 probe flushed by the tick
[  14.5s] settings ← {"ambient_pursuit":"away"}
[  16.7s] shot 00-settings-pursuit-away.png
[  16.7s] settings ← {"ambient_pursuit":"away","ambient_quiet_hours":["22:22","22:52"]}
[  25.4s] shot 01-away-watching-toast-no-external.png
[  29.5s] PASS  §14f-45  away + watching → toast fires, external channels HELD
[  29.5s]       toast: shown | smtp +0 | webhook +0 | ledger: null
[  29.5s] settings ← {"ambient_pursuit":"away","ambient_quiet_hours":["22:22","22:52"]}
[  29.6s] # browser off the app; waiting for the SSE stream to unregister
[  61.9s] PASS  §14f-46  away + nobody watching → both external channels PURSUE
[  61.9s]       smtp +1 | webhook +1 | ledger: {"email":{"at":"2026-09-10T20:22:51.211865+00:00","ok":true,"dead":false,"error":null,"attempts":1,"next_attempt_at":null},"in_app":{"at":"2026-09-10T20:22:51.202079+00:00","ok":false,"error":"no subscriber"},"webhook":{"at":"2026-09-10T20:22:51.222555+00:00","ok":true,"dead":false,"error":null,"attempts":1,"next_attempt_at":null}}
[  61.9s]   --- the SMTP sink actually received ---
  from=<concierge@local> to=["<owner@local>"]
  Subject: [concierge] ambient interrupt: 1 item(s)
  • [ops · urgency 5] PURSUIT 46: away + nobody watching
[  61.9s]   --- the SMS-gateway-shaped webhook sink actually received ---
  POST /push  {"kind":"ambient_delivery","mode":"interrupt","items":[{"id":"3a066244-25d6-4589-8c93-ede60a059b10","category":"ops","tier":0,"urgency":5,"title":"PURSUIT 46: away + nobody watching","body":"pursuit matrix"}]}
[  61.9s] settings ← {"ambient_pursuit":"away","ambient_quiet_hours":["20:17","21:22"]}
[  61.9s] # browser off the app; waiting for the SSE stream to unregister
[ 119.2s] PASS  §14f-47a quiet hours over now beat pursuit → demoted, NOTHING sent
[ 119.2s]       tier 2 (seeded at 0) | delivered_at null | smtp +0 | webhook +0
[ 119.2s] settings ← {"ambient_pursuit":"off","ambient_quiet_hours":["22:23","22:53"]}
[ 119.3s] # browser off the app; waiting for the SSE stream to unregister
[ 151.6s] PASS  §14f-47b pursuit 'off' + nobody watching → in-app only, nothing external
[ 151.6s]       delivered in-app: yes | smtp +0 | webhook +0 | ledger: {"in_app":{"at":"2026-09-10T20:24:21.483907+00:00","ok":false,"error":"no subscriber"}}
[ 151.6s] settings ← {"ambient_pursuit":"always","ambient_quiet_hours":["22:24","22:54"]}
[ 164.8s] PASS  §14f-47c pursuit 'always' + watching → external fires anyway (pre-M41 default)
[ 164.8s]       smtp +1 | webhook +1 | ledger: {"email":{"at":"2026-09-10T20:24:36.544096+00:00","ok":true,"dead":false,"error":null,"attempts":1,"next_attempt_at":null},"webhook":{"at":"2026-09-10T20:24:36.555313+00:00","ok":true,"dead":false,"error":null,"attempts":1,"next_attempt_at":null}}
[ 168.0s] shot 02-inbox-pursued-deliveries.png
[ 168.0s] settings ← {"ambient_pursuit":"off","ambient_quiet_hours":["22:14","22:44"],"ambient_notification_budget_per_day":40,"ambient_channels":{"interrupt":["in_app","email","webhook"]},"ambient_tick_interval_s":15}
[ 168.0s] # restored: pursuit=off quiet=["22:14","22:44"] channels={"interrupt":["in_app","email","webhook"]}
[ 168.0s] # 5/5 scenarios passed
[ 168.0s] # end — 2026-09-10T20:24:44.262Z
```
