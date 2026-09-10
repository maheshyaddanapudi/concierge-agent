# §14q-92 — a delivery reaches subscribers on every replica

Three `curl -N /ambient/stream` subscribers pinned to the three host ports, then two Chromium pages through the balancer (`browsers.log` section below).

```
# §14q-92 — a delivery reaches subscribers on every replica — 2026-09-03T00:43:23Z

$ PATCH /settings: ambient on, tick 15 s, webhook on the interrupt mode, pursuit=away
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_channels': {'interrupt': ['webhook']}, 'ambient_pursuit': 'away', 'ambient_quiet_hours': []}
ambient leader: backend-1 (concierge_ambient_leader=1 there)

$ three subscribers, one pinned to each host port (curl -N /ambient/stream)

$ GET /replicas: subscribers per replica (the cluster audience the oracle will count)
[('53ca6c1b373e', 1), ('ff318a532d30', 1), ('5deb830a6522', 1)]
stream 1 first ping: data: {"replica": "53ca6c1b373e"}
stream 2 first ping: data: {"replica": "ff318a532d30"}
stream 3 first ping: data: {"replica": "5deb830a6522"}

$ a tier-0 interrupt queued from replica backend-2 (NOT the leader) via add_delivery — the leader's next tick flushes it
the delivery event is on all three streams after 9363 ms
-- stream on :8007
id: 1 event: delivery 
   replica 53ca6c1b373e mode interrupt title M54 FLEET TOAST: payments-api p99 4.1 s on replica set
-- stream on :8008
id: 1 event: delivery 
   replica ff318a532d30 mode interrupt title M54 FLEET TOAST: payments-api p99 4.1 s on replica set
-- stream on :8009
id: 1 event: delivery 
   replica 5deb830a6522 mode interrupt title M54 FLEET TOAST: payments-api p99 4.1 s on replica set

$ the leader's log: watchers = the cluster audience (3, on a leader with 1 local), pursuit held the webhook
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "pursuit": "away", "watchers": 3, "channels": ["webhook"], "event": "ambient_pursuit_held" @ 2026-09-03T00:43:51.956195Z
webhook receiver so far: 0 POSTs

$ a routine fired through replica 2 on the live model executes on the leader (the ambient run plane is the cluster's)
fire → {'status': 'accepted', 'event_id': '8669680f-c328-4ac2-9d43-4d7a62f2168f'}
verdict 'fired' after 1x0.5s
routine run: completed on 5deb830a6522 (leader is 53ca6c1b373e)

$ close all three subscribers → the next interrupt reaches nobody in-app → pursuit=away sends the webhook (the receiver logs the envelope)
subscribers now [('53ca6c1b373e', 0), ('ff318a532d30', 0), ('5deb830a6522', 0)]
webhook received after 25x0.25s
HOOK /hook {"kind": "ambient_delivery", "mode": "interrupt", "items": [{"id": "9c5d9f2b-61f4-48d2-87d7-e3f001426885", "category": "ops", "tier": 0, "urgency": 5, "title": "M54 FLEET WEBHOOK: nobody watching", "body": "Second tier-0 interrupt; every subscriber is gone."}]}
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "pursuit": "away", "watchers": 3, "channels": ["webhook"], "event": "ambient_pursuit_held" @ 2026-09-03T00:43:51.956195Z
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["9c5d9f2b-61f4-48d2-87d7-e3f001426885"], "event": "ambient_delivered_unseen" @ 2026-09-03T00:44:23.552085Z

$ cleanup: routine paused, pursuit back to always, channels off
paused
# end §92 — 2026-09-03T00:44:23Z
```

## Two browsers through the balancer (Playwright)

```
probe streams answered by 5deb830a6522 and ff318a532d30
waiting 12 s for a heartbeat to carry the subscriber counts to the fleet table
GET /replicas subscribers: [["53ca6c1b373e",0],["ff318a532d30",1],["5deb830a6522",1]]
ambient leader on host port 8007; queuing the tier-0 interrupt on backend-2 (:8008, not the leader)
toast visible in BOTH browsers 2188 ms after the queue (one leader tick ≤ 15 s + fan-out)
A toaster: ambient interrupt · ops×M54 BROWSER TOAST: checkout error rate 6.2% across the replica set
B toaster: ambient interrupt · ops×M54 BROWSER TOAST: checkout error rate 6.2% across the replica set
```
