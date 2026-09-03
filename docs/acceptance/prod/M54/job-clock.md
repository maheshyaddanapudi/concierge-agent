# §14q-93 — consolidation runs once per interval cluster-wide

Memory on, three replicas, `job_clock` truncated so every job is due at once; then a replica restart; then the clock advanced by hand past every interval.

```
# §14q-93 — consolidation runs once per interval cluster-wide — 2026-09-03T00:47:37Z

$ PATCH /settings: memory on (all jobs gated on), retention gates on
{'memory_enabled': True, 'retention_ambient_events_enabled': True, 'retention_deliveries_enabled': True, 'retention_ambient_policies_enabled': False, 'retention_pattern_instances_enabled': False, 'retention_a2a_tasks_enabled': False, 'retention_auth_sessions_enabled': True}

$ psql: truncate job_clock (every job becomes due at once on all three replicas)
TRUNCATE TABLE
T0=2026-09-03T00:47:37Z — the periodic loop ticks every 60 s on each replica; waiting 75 s

$ job_clock after one interval: each job ran once
memory:communities|00:47:37
memory:compact|00:47:37
memory:contradict|00:47:37
memory:decay|00:47:37
memory:mine|00:47:37
ratelimit:evict|00:47:38
retention|00:47:38

$ the three logs together: each job's line appears once (memory_decay / memory_reflection / retention_*)
backend-1: decay=0 contradict=0 compact=0 communities=0 backfill=0 retention=0
backend-2: decay=1 contradict=1 compact=1 communities=0 backfill=0 retention=0
backend-3: decay=0 contradict=0 compact=0 communities=0 backfill=0 retention=0
(a job that logs nothing when it finds no work still stamps job_clock — the table is the clock, the log is the narrative)

$ docker restart backend-2 → its boot tick re-runs nothing (job_clock unchanged, no new job lines)
backend-2 ready again after 4s
job_clock unchanged across the restart: memory:communities@00:47:37,memory:compact@00:47:37,memory:contradict@00:47:37,memory:decay@00:47:37,memory:mine@00:47:37,ratelimit:evict@00:47:38,retention@00:47:38
backend-2 job lines since its restart: 0 (memory_periodic ticked: 0 loop-tick lines)

$ advance the clock by hand (last_run_at − 25 h: past every interval, contradict's 24 h included) → exactly one replica runs each job on the next tick
UPDATE 7
memory:communities|00:49:36
memory:compact|00:49:36
memory:contradict|00:49:36
memory:decay|00:49:36
memory:mine|00:49:36
ratelimit:evict|00:49:36
retention|00:49:36
backend-1 since 2026-09-03T00:49:05Z: decay=1 contradict=1 compact=1 retention=0
backend-2 since 2026-09-03T00:49:05Z: decay=0 contradict=0 compact=0 retention=0
backend-3 since 2026-09-03T00:49:05Z: decay=0 contradict=0 compact=0 retention=0
(reflect, backfill and extract_tune have their own §3.7.1 gates — memory_reflection_enabled, embedding_model, memory_extraction_learning — off here, so they never become rows)

$ cleanup: memory off, retention gates off
# end §93 — 2026-09-03T00:50:16Z
```
