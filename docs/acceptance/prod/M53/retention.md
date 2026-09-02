# §14p-85 — retention deletes only behind its own switch

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, formatter off, ambient on. One continuous driver run on 2026-09-02T02:51:13Z against backend container `4e7d2b99e05d` (the sections below are that run's transcript, verbatim, split per §14p item; the driver is a sandbox script of `curl`, `psql` and `docker compose` calls). Times are UTC.

```
$ psql: seed one finished row and one protected row per table, aged 400 days
INSERT 0 2
INSERT 0 2
INSERT 0 2
INSERT 0 2
INSERT 0 2
INSERT 0 2

$ rows seeded:
events=2 deliveries=2 policies=2 patterns=2 a2a=2 sessions=2

$ GET /retention (gates as shipped: five off, auth_sessions on) — eligible counted regardless
ambient_events       enabled=False days=30   eligible=1
deliveries           enabled=False days=90   eligible=1
ambient_policies     enabled=False days=365  eligible=1
pattern_instances    enabled=False days=7    eligible=1
a2a_tasks            enabled=False days=90   eligible=1
auth_sessions        enabled=True  days=7    eligible=1

$ POST /retention/run with the gates as shipped
{'deleted': {'ambient_events': 0, 'deliveries': 0, 'ambient_policies': 0, 'pattern_instances': 0, 'a2a_tasks': 0, 'auth_sessions': 1}}

$ rows after: only the expired session is gone
events=2 deliveries=2 policies=2 patterns=2 a2a=2 sessions=1

$ PATCH /settings: every retention gate on
HTTP 200

$ POST /retention/run
{'deleted': {'ambient_events': 1, 'deliveries': 1, 'ambient_policies': 1, 'pattern_instances': 1, 'a2a_tasks': 1, 'auth_sessions': 0}}

$ rows after: one protected row per table survives
events=1 deliveries=1 policies=1 patterns=1 a2a=1 sessions=1
events|
deliveries|m53 old pending
policies|latest
patterns|armed
a2a|parked
sessions|m53hash-live

$ GET /metrics retention counter
concierge_retention_deleted_total{table="auth_sessions"} 1.0
concierge_retention_deleted_total{table="ambient_events"} 1.0
concierge_retention_deleted_total{table="deliveries"} 1.0
concierge_retention_deleted_total{table="ambient_policies"} 1.0
concierge_retention_deleted_total{table="pattern_instances"} 1.0
concierge_retention_deleted_total{table="a2a_tasks"} 1.0

$ PATCH /settings: gates back to shipped defaults; PATCH retention_deliveries_days=0 → 422
HTTP 200
{"detail":"retention_deliveries_days must be an integer number of days between 1 and 3650"}
HTTP 422
```
