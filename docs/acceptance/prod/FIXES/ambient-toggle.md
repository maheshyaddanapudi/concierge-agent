# finding 2 re-verified — 2026-09-10T23:48:42Z

$ initial settings: {"ambient_enabled": true, "ambient_tick_interval_s": 15, "ambient_notification_budget_per_day": 3}

$ settings ← ambient_enabled=true, ambient_tick_interval_s=15, ambient_notification_budget_per_day=50 (so every probe can interrupt)
{'ambient_enabled': True, 'ambient_tick_interval_s': 15, 'ambient_notification_budget_per_day': 50}
the loop picks the new interval up after its current wait — one old interval at most
baseline: lease=1 gauge=1.0 acquired_lines=1 crash_lines=0
probe 'baseline: tick alive' flushed by the tick after 11s

$ switch cycle 1: off, 1s, on (the Settings switch)
waiting two ticks (30s)
after switch cycle 1: lease=1 gauge=1.0 acquired_lines=1 crash_lines=0
a tick landed inside the dark second: no — the loop never saw it dark
probe 'switch cycle 1: tick alive after off→on' flushed by the tick after 12s

$ switch cycle 2: off, 1s, on (the Settings switch)
waiting two ticks (30s)
after switch cycle 2: lease=1 gauge=1.0 acquired_lines=1 crash_lines=0
a tick landed inside the dark second: no — the loop never saw it dark
probe 'switch cycle 2: tick alive after off→on' flushed by the tick after 11s

$ held cycle 1: off for a full tick (18s) so the tick sees ambient dark, then on
while dark: lease=0 gauge=0.0 acquired_lines=1 crash_lines=0
waiting two ticks (30s)
after held cycle 1: lease=1 gauge=1.0 acquired_lines=2 crash_lines=0
re-acquired: yes (ambient_leader_acquired +1)
probe 'held cycle 1: tick alive after off→on' flushed by the tick after 10s

$ held cycle 2: off for a full tick (18s) so the tick sees ambient dark, then on
while dark: lease=0 gauge=0.0 acquired_lines=2 crash_lines=0
waiting two ticks (30s)
after held cycle 2: lease=1 gauge=1.0 acquired_lines=3 crash_lines=0
re-acquired: yes (ambient_leader_acquired +1)
probe 'held cycle 2: tick alive after off→on' flushed by the tick after 10s

$ the loop's own log lines during the drill
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["5d017161-ee45-49f0-b3b0-c25ea106a47a"], "event": "ambient_delivered_un
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["f349f424-997b-4fd5-b6cc-bf88196edcb8"], "event": "ambient_delivered_un
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["9cfe882b-49a7-4685-bcea-2f86ec288dd1"], "event": "ambient_delivered_un
{"tier": "ambient", "kind": "leader", "event": "ambient_leader_acquired", "level": "info", "timestamp": "2026-09-10T23:50:54.488843Z"}
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["a353b389-f5de-47c2-ac4e-739ec6313da5"], "event": "ambient_delivered_un
{"tier": "ambient", "kind": "leader", "event": "ambient_leader_acquired", "level": "info", "timestamp": "2026-09-10T23:51:54.731472Z"}
{"tier": "ambient", "kind": "deliver", "mode": "interrupt", "count": 1, "delivery_ids": ["87e0d96c-4413-4a20-a301-7baf9986d360"], "event": "ambient_delivered_un

$ settings restored ← {"ambient_enabled": true, "ambient_tick_interval_s": 15, "ambient_notification_budget_per_day": 3}

$ verdict: lease=1 gauge=1.0 crash_lines=0 — the tick leads after every off→on cycle
