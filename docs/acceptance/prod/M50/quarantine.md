# §14m-68 — a broken routine is quarantined, the tick keeps ticking

Captured 2026-09-01T23:11:30Z on the rebuilt stack (image from the M50 tree, migration `q6e7f8a9b0c1` applied). Transcript of `m50-quarantine.sh` — the driver is a plain curl/psql script.

```

$ PATCH /settings ambient on, tick 15s
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_timezone': 'Europe/Lisbon'}

$ POST /routines {"name":"m50-bad-once","prompt":"p","triggers":[{"type":"once","at":"not-a-date"}]}
{"detail":[{"type":"datetime_from_date_parsing","loc":["body","triggers",0,"once","at"],"msg":"Input should be a valid datetime or date, invalid character in year","input":"not-a-date","ctx":{"error":"invalid character in year"}}]}
HTTP 422

$ POST /routines {"name":"m50-bad-interval","prompt":"p","triggers":[{"type":"interval","seconds":5}]}
{"detail":[{"type":"greater_than_equal","loc":["body","triggers",0,"interval","seconds"],"msg":"Input should be greater than or equal to 60","input":5,"ctx":{"ge":60}}]}
HTTP 422

$ POST /routines {"name":"m50-bad-cron","prompt":"p","triggers":[{"type":"cron","cron":"bogus"}]}
{"detail":[{"type":"value_error","loc":["body","triggers",0,"cron","cron"],"msg":"Value error, not a valid cron expression: 'bogus'","input":"bogus","ctx":{"error":{}}}]}
HTTP 422

$ POST /routines {"name":"m50-bad-filter","prompt":"p","triggers":[{"type":"webhook","filters":[{"field":"x","op":"nope","value":"1"}]}]}
{"detail":[{"type":"literal_error","loc":["body","triggers",0,"webhook","filters",0,"op"],"msg":"Input should be 'equals', 'contains', 'starts_with', 'one_of' or 'regex'","input":"nope","ctx":{"expected":"'equals', 'contains', 'starts_with', 'one_of' or 'regex'"}}]}
HTTP 422

$ POST /routines m50-broken-trigger (valid once trigger — corrupted below, past the API)
id=6b8bff65-ef22-45c7-9c23-75298ac080e5

$ POST /routines m50-healthy (interval 3600)
id=5e68f9c0-a49a-48fe-acb0-fc7899ed25e3

$ UPDATE routines SET triggers = garbage once.at  (direct SQL — the shape the API now refuses)
UPDATE 1

$ waiting for three ticks (15 s each) …
quarantined after ~66s

$ GET /routines/6b8bff65-ef22-45c7-9c23-75298ac080e5 (broken)
{'name': 'm50-broken-trigger', 'status': 'error', 'status_reason': "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", 'consecutive_failures': 3, 'last_fired_at': None}

$ GET /routines/5e68f9c0-a49a-48fe-acb0-fc7899ed25e3 (healthy — fired on the same ticks)
{'name': 'm50-healthy', 'status': 'active', 'consecutive_failures': 0, 'last_fired_at': '2026-09-01T23:12:05.875668+00:00'}

$ GET /metrics | grep evaluator_errors
concierge_ambient_evaluator_errors_total{evaluator="schedule_routine",kind="error"} 3.0

$ backend log: ambient_trigger_failed
{"tier": "ambient", "kind": "schedule", "routine": "6b8bff65-ef22-45c7-9c23-75298ac080e5", "failures": 1, "quarantined": false, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "warning", "timestamp": "2026-09-01T23:12
{"tier": "ambient", "kind": "schedule", "routine": "6b8bff65-ef22-45c7-9c23-75298ac080e5", "failures": 2, "quarantined": false, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "warning", "timestamp": "2026-09-01T23:12
{"tier": "ambient", "kind": "schedule", "routine": "6b8bff65-ef22-45c7-9c23-75298ac080e5", "failures": 3, "quarantined": true, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "warning", "timestamp": "2026-09-01T23:12:
```
