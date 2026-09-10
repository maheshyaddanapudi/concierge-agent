# M50 quarantine + timezone drill — 2026-09-10T21:27:54Z

$ PATCH /settings ambient on, tick 15 s, ambient_timezone Europe/Lisbon
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_timezone': 'Europe/Lisbon'}
default_model (the healthy routine runs on it): openrouter:qwen/qwen3.8-max

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

$ POST /routines m50-broken-trigger (a valid once trigger — corrupted below, past the API)
id=af3c6cdb-1b39-4e99-a44b-87ec734d8533

$ POST /routines m50-healthy (interval 3600)
id=9379dc65-e3cd-4775-afb7-599b4527df41

$ UPDATE routines SET triggers = garbage once.at (direct SQL — the shape the API now refuses)
UPDATE 1

$ waiting for three ticks (15 s each): the broken routine is quarantined, the healthy one fires on the same ticks
broken routine status='error' after 45s

$ GET /routines/af3c6cdb-1b39-4e99-a44b-87ec734d8533 (broken)
{'name': 'm50-broken-trigger', 'status': 'error', 'status_reason': "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", 'consecutive_failures': 3, 'last_fired_at': None}

$ GET /routines/9379dc65-e3cd-4775-afb7-599b4527df41 (healthy — fired on the same ticks)
{'name': 'm50-healthy', 'status': 'active', 'consecutive_failures': 0, 'last_fired_at': '2026-09-10T21:28:09.668151+00:00'}

$ GET /metrics | grep evaluator_errors
concierge_ambient_evaluator_errors_total{evaluator="schedule_routine",kind="error"} 3.0

$ backend log: ambient_trigger_failed (failures 1 → 2 → 3, quarantined on the third)
{"tier": "ambient", "kind": "schedule", "routine": "af3c6cdb-1b39-4e99-a44b-87ec734d8533", "failures": 1, "quarantined": false, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "
{"tier": "ambient", "kind": "schedule", "routine": "af3c6cdb-1b39-4e99-a44b-87ec734d8533", "failures": 2, "quarantined": false, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "
{"tier": "ambient", "kind": "schedule", "routine": "af3c6cdb-1b39-4e99-a44b-87ec734d8533", "failures": 3, "quarantined": true, "error": "trigger evaluation failed: ValueError: Invalid isoformat string: 'garbage'", "event": "ambient_trigger_failed", "level": "w

$ the tick keeps ticking: the healthy routine's run
[('6a7b43fc', 'completed')]
shot 02-ambient-routines-quarantined.png

$ §14m-69 PATCH /settings ambient_timezone=Europe/Lisbon → 200; Mars/Olympus → 422; 7 → 422
Europe/Lisbon → HTTP 200
{"detail":"ambient_timezone: unknown IANA zone 'Mars/Olympus'"} → HTTP 422
{"detail":"ambient_timezone must be an IANA zone name string (e.g. Europe/Lisbon)"} → HTTP 422
ambient_timezone = Europe/Lisbon | the quiet hours it governs: []
shot 03-settings-ambient-timezone.png

$ the zone logic's contract tests (a dev checkout — the image ships no pytest): tests/test_m50_ceiling.py -k 'timezone or quiet or digest or zone'
ERROR tests/test_m50_ceiling.py::test_effective_settings_carry_the_zone[asyncio]
ERROR tests/test_m50_ceiling.py::test_quiet_hours_resolve_in_the_configured_zone
16 deselected, 4 errors in 3.54s

(ACC_M50_HARNESS=1 re-runs the sse,runs-scale harness record; the 01-runs-page-paged-under-load frame needs that 10k-run table)

$ cleanup: routines deleted; tick back to 60 s, timezone UTC
DELETE broken → HTTP 204
DELETE healthy → HTTP 204
# end — 2026-09-10T21:28:54Z
