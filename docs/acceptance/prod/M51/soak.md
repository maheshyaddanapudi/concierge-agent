# Soak — ambient enabled for 30 minutes, resident memory sampled

The exit criterion is "ambient enabled for an extended run with flat RSS". Load for the
window: an interval routine (`m51-soak`, every 60 s) on the fake provider, a webhook fire
every 10 s, a chat run every 30 s; the M51 delivery-retry driver and its webhook retries
ran during the first two minutes of the same window. Resident memory is
`process_resident_memory_bytes` from `/metrics` (the `docker stats` column is the cgroup
figure, which includes page cache), sampled every ~30 s. `soak.csv` is the raw record.

| phase | RSS |
|---|---|
| first sample (t = 22 s) | 247.7 MB |
| t ≈ 5 min | 264.2 MB (+16.5 MB — warm-up: first runs, checkpointer pool, event bus) |
| t ≈ 10 min | 268.1 MB (+3.9 MB) |
| t ≈ 15 min | 268.6 MB (+0.5 MB) |
| last sample (t = 1774 s) | 269.7 MB (+1.1 MB over the final 15 min) |
| max | 269.7 MB |

Over the whole window the process grew +22.0 MB; over the second half it grew
+1.1 MB while running 103 runs in total, delivering
49 outbox rows and holding open file descriptors flat
(35.0 → 33.0). The bounded `RunEventBus` (500 runs, 15-min TTL) is the reason the
per-run state stops accumulating after the first quarter hour.

Two honest notes. The webhook fires stopped being accepted after 50 events: the §17.3a
per-routine kill switch (`RULE_KILL_SWITCH_PER_HOUR = 50`) answered every later fire with
`429 Too Many Requests` — the guard doing its job, which is why the `events_total` column
plateaus at 51 while runs and deliveries keep climbing on the interval trigger and the chat
loop. And the run-status tally at the end (`cancelled 4`, `failed 6`, `completed 119`) is
the whole day's table: the four cancels are the two drained runs and the two screenshot
runs, the six failures are the wall-clock run, the 429 run and the four SIGKILL orphans
from the fault-injection transcripts — no run was left `running` or `queued`.

```text
$ PATCH /settings ambient on (fake provider), tick 15 s
{'ambient_enabled': True, 'default_model': 'fake:scripted', 'ambient_runs_per_day': 5000}

$ POST /routines — interval 60 s + webhook trigger
routine=b135a289-1400-4919-a6a2-0ce947e5fdd8
fire token issued (47 chars)
22,247.7,339.9MiB,26,4,47,35.0
53,256.1,344.3MiB,30,7,50,35.0
84,257.1,345.3MiB,34,10,53,36.0
116,257.9,346MiB,38,13,56,36.0
147,258.3,346.9MiB,42,16,59,36.0
178,259.1,347.3MiB,46,19,62,36.0
210,261.6,349.7MiB,50,22,65,36.0
241,263.7,352.1MiB,54,25,68,36.0
272,263.8,352.2MiB,58,28,71,36.0
304,264.2,352.7MiB,62,31,74,36.0
335,264.4,352.4MiB,66,34,77,36.0
366,264.7,353.4MiB,70,37,80,37.0
398,265.1,353.3MiB,74,40,83,38.0
429,267.4,356.1MiB,78,43,86,39.0
460,267.6,355.7MiB,82,46,89,34.0
491,267.7,356.2MiB,86,49,92,33.0
523,267.8,356.4MiB,89,51,95,33.0
554,267.9,356.4MiB,90,51,96,33.0
585,267.9,356.8MiB,91,51,96,33.0
617,268.1,356.6MiB,92,51,96,33.0
648,268.2,356.5MiB,93,51,96,33.0
679,268.3,356.8MiB,94,51,96,33.0
711,268.3,357.1MiB,95,51,96,33.0
742,268.3,356.8MiB,96,51,96,33.0
773,268.3,356.9MiB,97,51,96,33.0
804,268.3,357.2MiB,98,51,96,33.0
836,268.3,357MiB,99,51,96,33.0
867,268.4,357MiB,100,51,96,33.0
898,268.6,357MiB,101,51,96,33.0
929,268.6,357.1MiB,102,51,96,33.0
961,268.7,357.2MiB,103,51,96,33.0
992,268.8,357.5MiB,104,51,96,33.0
1023,268.8,357.5MiB,105,51,96,33.0
1055,268.9,357.4MiB,106,51,96,33.0
1086,268.9,357.6MiB,107,51,96,33.0
1117,268.9,357.6MiB,108,51,96,33.0
1148,268.9,358MiB,109,51,96,34.0
1180,268.9,357.8MiB,110,51,96,33.0
1211,268.9,358.1MiB,111,51,96,33.0
1242,269.2,357.7MiB,112,51,96,33.0
1274,269.2,357.7MiB,113,51,96,33.0
1305,269.2,358.2MiB,114,51,96,33.0
1336,269.3,358.3MiB,115,51,96,33.0
1367,269.3,358.1MiB,116,51,96,33.0
1399,269.3,358.2MiB,117,51,96,33.0
1430,269.3,358.3MiB,118,51,96,33.0
1461,269.3,358.6MiB,119,51,96,33.0
1492,269.3,358.5MiB,120,51,96,33.0
1524,269.3,358.6MiB,121,51,96,33.0
1555,269.3,358.6MiB,122,51,96,33.0
1586,269.4,358.6MiB,123,51,96,33.0
1618,269.7,358.8MiB,124,51,96,33.0
1649,269.7,358.8MiB,125,51,96,33.0
1680,269.7,358.9MiB,126,51,96,33.0
1711,269.7,359.1MiB,127,51,96,33.0
1743,269.7,359.3MiB,128,51,96,33.0
1774,269.7,359.3MiB,129,51,96,33.0

$ summary
samples=57 duration=1774s
rss first=247.7 MB  max=269.7 MB  last=269.7 MB  drift=+22.0 MB
runs 26→129  events 4→51  deliveries 47→96  fds 35.0→33.0

$ routine after the soak
{'name': 'm51-soak', 'status': 'active', 'status_reason': None, 'consecutive_failures': 0, 'last_fired_at': '2026-09-02T00:24:00.057270+00:00'}

$ non-terminal runs
cancelled|4
completed|119
failed|6
```
