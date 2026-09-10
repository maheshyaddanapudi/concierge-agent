# §14r-97 — first pass (the run stream leaked across tenants)

Kept verbatim: every REST surface answered `carol@globex` with 404 while `GET /chat/stream/{run}` streamed alice's whole record to her (`→ HTTP 200` after the seven events under "the record stream follows the same rule"). Fixed in the same wave; `seam-drill.md` is the pass after the fix.

```
# M55 seam drill — 2026-09-10T01:05:19Z

$ AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub docker compose up -d --force-recreate backend
 Container concierge-agent-backend-1 Started 
ready after 6s on :8002

$ no identity → 401 on the API; /health and /ready stay open
GET /tools (no headers) → HTTP 401
GET /health → HTTP 200

$ the builtin's login route is not offered by another provider
{"detail":"login is not offered by the active auth provider"} → HTTP 404

$ writes need the stub's editor role: bob@acme (member) PATCH /settings → 403 with the stub's reason; alice@acme (editor) → 200
{"detail":"stub: registry and settings writes need the editor role"} → HTTP 403
{'default_model': 'openrouter:qwen/qwen3.8-max', 'memory_enabled': True} → HTTP 200

$ alice@acme starts a chat run on the live model
run dde1243f-44d4-448f-b8d1-5b49acce0fda
completed|21623525-0eb0-5f37-8bf2-e203d4223e13|A Postgres advisory lock guarantees only that at most one session holding the same lock key (in the same lock 
alice's id per the stub: 21623525-0eb0-5f37-8bf2-e203d4223e13

$ the run is bob@acme's to see (same tenant) and invisible to carol@globex
GET /runs/{id} as bob@acme → HTTP 200
{"detail":"run not found"} → HTTP 404
GET /runs as carol@globex → 0 runs
GET /conversations as bob@acme → ['In one sentence: what does a Postgres ad']
GET /conversations as carol@globex → []

$ the record stream follows the same rule
bob@acme stream events: 7
id: 1
event: run_status
data: {"type": "run_status", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:29.422870+00:00", "payload": {"status": "running"}, "seq": 1}

id: 2
event: activity
data: {"type": "activity", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:32.101941+00:00", "payload": {"step_id": "4585500d-eb2b-448c-b10c-80f6fd4ece30", "parent_step_id": null, "step_type": "plan", "tier": "orchestrator", "kind": null, "entity_name": null, "node_id": null, "status": "running"}, "seq": 2}

id: 3
event: activity
data: {"type": "activity", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:37.769437+00:00", "payload": {"step_id": "4585500d-eb2b-448c-b10c-80f6fd4ece30", "status": "completed"}, "seq": 3}

id: 4
event: plan
data: {"type": "plan", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:37.769480+00:00", "payload": {"entries": [], "mode": "graph"}, "seq": 4}

id: 5
event: token
data: {"type": "token", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:37.772373+00:00", "payload": {"text": "A Postgres advisory lock guarantees only that at most one session holding the same lock key (in the same lock mode) proceeds at a time \u2014 it's a purely application-defined, cooperative mutex that Postgres itself enforces no semantics on, so it protects nothing unless every code path voluntarily acquires it."}, "seq": 5}

id: 6
event: run_status
data: {"type": "run_status", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:37.788603+00:00", "payload": {"status": "completed"}, "seq": 6}

id: 7
event: done
data: {"type": "done", "run_id": "dde1243f-44d4-448f-b8d1-5b49acce0fda", "ts": "2026-09-10T01:05:37.788627+00:00", "payload": {"answer": "A Postgres advisory lock guarantees only that at most one session holding the same lock key (in the same lock mode) proceeds at a time \u2014 it's a purely application-defined, cooperative mutex that Postgres itself enforces no semantics on, so it protects nothing unless every code path voluntarily acquires it.", "tokens": {"input_tokens": 1227, "output_tokens": 153}}, "seq": 7}

 → HTTP 200

$ memory: alice@acme stores a fact; bob@acme recalls it; carol@globex cannot
memory ba4ea679-a709-4aa8-ac58-710a8a74db1d owner 21623525-0eb0-5f37-8bf2-e203d4223e13
bob@acme recall → ['the acme roadmap ships pgvector recall in Q4']
carol@globex recall → []

$ the default provider back (AUTH_PROVIDER unset): byte-identical single-user — no identity needed, no headers, the builtin's login answers 409 while dark
 Container concierge-agent-backend-1 Started 
ready after 6s on :8003
HTTP/1.1 200 OK
{"detail":"auth is disabled (AUTH_ENABLED=false)"} → HTTP 409
GET /runs/{id} with no identity → HTTP 200
# end — 2026-09-10T01:05:48Z
```
