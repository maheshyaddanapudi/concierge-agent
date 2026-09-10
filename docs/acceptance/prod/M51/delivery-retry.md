# §14n-75 — delivery dispatches before it commits, then retries with backoff until it dead-letters

The webhook channel points at a closed port (`AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook` in the backend env, so every send is refused at once). One tier-0 delivery is inserted through the app's own `add_delivery` inside the backend container; the running server's tick (15 s) flushes it — dispatch first, then the commit that marks it delivered together with the channel ledger. Attempt 2 lands on the real clock after the 60 s backoff. The 5-min and 30-min backoffs before attempts 3 and 4 are skipped by moving `next_attempt_at` into the past — a clock skip, stated as such, not a code path — and the fourth attempt dead-letters the entry. A further clock skip changes nothing: `at` stays at the fourth attempt and no send happens. Captured by `m51-delivery.sh`; the two log lines are the server's own `ambient_channel_failed` / `ambient_channel_retry` records for this row.

```text
$ backend env: AMBIENT_WEBHOOK_URL
http://127.0.0.1:9/hook

$ PATCH /settings ambient on, tick 15 s, quiet hours off, interrupt → in_app + webhook
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_channels': {'interrupt': ['in_app', 'webhook']}, 'ambient_quiet_hours': []}

$ GET /metrics delivery_sends (before)
(none yet)

$ insert one pending tier-0 delivery through add_delivery (inside the backend container)
delivery=0d9322f1-de23-459a-b752-44e66b934019
00:15:07|||

$ wait for the tick to flush it (≤ 15 s): dispatched → webhook refused → committed delivered with the ledger
attempts=1 after 13s
00:15:21|00:15:20|interrupt|{"at": "2026-09-02T00:15:20.710644+00:00", "ok": false, "dead": false, "error": "All connection attempts failed", "attempts": 1, "next_attempt_at": "2026-09-02T00:16:20.710644+00:00"}

$ backend log: ambient_channel_failed
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "error": "All connection attempts failed", "attempts": 1, "next_attempt_at": "2026-09-02T00:16:20.710644+00:00", "event": "ambient_channel_failed", "level": "warning", "timestamp": "2026-09-02T00:15:20.710724Z"}
$ attempt 2 on the real clock: backoff 60 s, retried on the first tick after it is due
attempts=2 after 64s
00:16:31|00:15:20|interrupt|{"at": "2026-09-02T00:16:31.613122+00:00", "ok": false, "dead": false, "error": "All connection attempts failed", "attempts": 2, "next_attempt_at": "2026-09-02T00:21:31.613122+00:00"}

$ attempts 3 and 4: the 5-min and 30-min backoffs are skipped by moving next_attempt_at into the past (clock skip, not a code path)
attempts=3 after 10s
00:16:42|00:15:20|interrupt|{"at": "2026-09-02T00:16:41.645867+00:00", "ok": false, "dead": false, "error": "All connection attempts failed", "attempts": 3, "next_attempt_at": "2026-09-02T00:46:41.645867+00:00"}
attempts=4 after 10s
00:16:52|00:15:20|interrupt|{"at": "2026-09-02T00:16:51.745107+00:00", "ok": false, "dead": true, "error": "All connection attempts failed", "attempts": 4, "next_attempt_at": null}

$ dead-lettered: next_attempt_at is null, dead=true — a further clock skip changes nothing
00:17:27|00:15:20|interrupt|{"at": "2026-09-02T00:16:51.745107+00:00", "ok": false, "dead": true, "error": "All connection attempts failed", "attempts": 4, "next_attempt_at": "2026-09-02T00:16:51.801408+00:00"}

$ GET /metrics delivery_sends (after)
concierge_delivery_sends_total{channel="webhook",status="retry"} 3.0
concierge_delivery_sends_total{channel="webhook",status="dead"} 1.0

$ backend log: ambient_channel_retry lines
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 2, "dead": false, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-02T00:16:31.635978Z"}
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 3, "dead": false, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-02T00:16:41.665932Z"}
{"tier": "ambient", "kind": "deliver", "channel": "webhook", "ok": false, "attempts": 4, "dead": true, "event": "ambient_channel_retry", "level": "info", "timestamp": "2026-09-02T00:16:51.770295Z"}
$ restore: ambient_channels={} (in-app only)
{}
```
