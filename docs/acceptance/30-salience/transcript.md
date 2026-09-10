```
[   0.0s] # 30-salience — 2026-09-10T19:48:41.042Z
[   0.0s] settings ← {"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_quiet_hours":[],"ambient_salience_mode":"auto","ambient_salience_min_urgency":3,"ambient_salience_learning":"off","ambient_pursuit":"off","ambient_channels":{}}
[   2.2s] shot 00-settings-salience-auto.png
[   2.2s] # mode=auto min_urgency=3 judge=openrouter:qwen/qwen3.8-max
[   2.2s] # browser off the app; waiting 25s for the SSE stream to unregister
[  27.4s] inserted: hot=c131ecbd-3145-489f-a6ef-de7de0aba657 cold=57694806-8d06-415e-a7e7-d2a64dab0ec7
[  27.4s] # nobody is watching the stream — waiting for the tick to flush + judge…
[  44.8s] §14g-48 in_app ledger (hot):  {"in_app":{"at":"2026-09-10T19:49:15.539167+00:00","ok":false,"error":"no subscriber"}}
[  44.8s] §14g-48 in_app ledger (cold): {"in_app":{"at":"2026-09-10T19:49:15.539167+00:00","ok":false,"error":"no subscriber"}}
[  44.8s] §14g-49 salience (hot):  {"at":"2026-09-10T19:49:22.019278+00:00","mode":"auto","prior":{"tier":0,"channel":"interrupt","seen_at":null,"delivered_at":"2026-09-10T19:49:15.530630+00:00"},"reason":"~9% of checkouts (one in eleven) failing for six minutes with no rollback and the on-call never paged is a live, revenue-impacting production failure that nobody is currently handling, so it needs a human now rather than a memory entry.","applied":true,"verdict":"escalate","decision":"applied","confidence":0.9,"decided_at":"2026-09-10T19:49:22.019289+00:00","decided_by":"system","memory_ids":[]}
[  44.8s] §14g-50 salience (cold): {"at":"2026-09-10T19:49:25.168642+00:00","mode":"auto","prior":{"tier":0,"channel":"interrupt","seen_at":null,"delivered_at":"2026-09-10T19:49:15.530630+00:00"},"reason":"A successful cache warm that finished in 41s with explicitly no anomalies and \"nothing to do\" is a self-closing success heartbeat carrying no durable state change or actionable fact.","applied":true,"verdict":"drop","decision":"applied","confidence":0.97,"decided_at":"2026-09-10T19:49:25.168653+00:00","decided_by":"system","memory_ids":[]}
[  44.8s]   tiers after the judge: hot=2 cold=0 (auto applies: escalate leads the digest, drop dismisses)
[  46.4s] unread badge: {"count":12,"attention":11}
[  46.6s] shot 01-unread-badge-nav.png
[  49.5s] shot 02-inbox-salience-verdicts.png
[  49.5s] digest preview: 5 payments-api p99 error rate 9.4% and rising | 5 PURSUIT 47a: quiet hours beat pursuit | 5 payments-api p99 error rate 9.4% and rising
[  49.7s] shot 03-digest-preview-led-by-escalated.png
[ 201.8s] after hovering: unread={"count":5,"attention":5} hot.seen_at=null cold.seen_at=2026-09-10T19:49:30.76454+00:00
[ 201.9s] shot 04-after-marking-seen.png
[ 201.9s] settings ← {"ambient_salience_mode":"off","ambient_tick_interval_s":15,"ambient_quiet_hours":["21:48","22:18"],"ambient_pursuit":"off"}
[ 201.9s] # end — 2026-09-10T19:52:02.974Z
```
