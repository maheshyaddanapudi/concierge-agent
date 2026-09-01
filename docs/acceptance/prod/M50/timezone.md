# §14m-69 — quiet hours mean local night (M50 `ambient_timezone`)

Captured 2026-09-01T23:10:02Z. Part 1 is the contract suite for the zone logic; part 2 (below) is the live stack.

## 1. Contract tests

```
$ pytest tests/test_m50_ceiling.py -k "timezone or quiet or digest or zone" -v
tests/test_m50_ceiling.py::test_ambient_timezone_setting[asyncio] PASSED
tests/test_m50_ceiling.py::test_digest_due_resolves_in_the_configured_zone[asyncio] PASSED
tests/test_m50_ceiling.py::test_effective_settings_carry_the_zone[asyncio] PASSED
tests/test_m50_ceiling.py::test_quiet_hours_resolve_in_the_configured_zone PASSED
======================= 4 passed, 16 deselected in 1.58s =======================
```

The four assertions in `test_quiet_hours_resolve_in_the_configured_zone`: the same instant, 06:30 UTC, is quiet under the 22:00–07:00 range in UTC and in America/New_York (02:30), and NOT quiet in Europe/Lisbon (07:30) or Asia/Tokyo (15:30). `test_digest_due_resolves_in_the_configured_zone`: a 09:00 digest at 08:30 UTC is due in Europe/Lisbon (09:30 local) and not in UTC.

## 2. The live setting

```
$ curl -X PATCH /api/v1/settings -d '{"ambient_timezone": "Europe/Lisbon"}'
ambient_timezone = Europe/Lisbon
HTTP 200

$ curl -X PATCH /api/v1/settings -d '{"ambient_timezone": "Mars/Olympus"}'
{"detail":"ambient_timezone: unknown IANA zone 'Mars/Olympus'"}
HTTP 422

$ curl -X PATCH /api/v1/settings -d '{"ambient_timezone": 7}'
{"detail":"ambient_timezone must be an IANA zone name string (e.g. Europe/Lisbon)"}
HTTP 422
```

With the zone set, the quiet-hours check the delivery flush runs is the one the contract tests pin: 22:00–07:00 is evaluated in Europe/Lisbon wall-clock time, so an alert raised at 06:30 UTC (07:30 Lisbon) flushes instead of holding until 07:00 UTC.
