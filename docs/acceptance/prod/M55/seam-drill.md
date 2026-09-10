# §14r-97 — the reference stub on the shipped stack

The image rebuilt with M55; the stub selected by environment only (`AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub` — the image ships its tests); three principals in two tenants; a chat run on `openrouter:qwen/qwen3.8-max`. Second pass, after the stream fix the first pass found. The duplicate conversation and memory in `bob@acme`'s lists are the first pass's rows, still in the database.

```
# M55 seam drill — 2026-09-10T01:08:35Z

$ AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub docker compose up -d --force-recreate backend
 Container concierge-agent-backend-1 Started 
ready after 6s on :8004

$ no identity → 401 on the API; /health and /ready stay open
GET /tools (no headers) → HTTP 401
GET /health → HTTP 200

$ the builtin's login route is not offered by another provider
{"detail":"login is not offered by the active auth provider"} → HTTP 404

$ writes need the stub's editor role: bob@acme (member) PATCH /settings → 403 with the stub's reason; alice@acme (editor) → 200
{"detail":"stub: registry and settings writes need the editor role"} → HTTP 403
{'default_model': 'openrouter:qwen/qwen3.8-max', 'memory_enabled': True} → HTTP 200

$ alice@acme starts a chat run on the live model
run fe9a60d0-b931-48b3-9a4f-61d919e95af3
completed|21623525-0eb0-5f37-8bf2-e203d4223e13|A Postgres advisory lock guarantees nothing about your tables or rows by itself — it only guarantees mutual ex
alice's id per the stub: 21623525-0eb0-5f37-8bf2-e203d4223e13

$ the run is bob@acme's to see (same tenant) and invisible to carol@globex
GET /runs/{id} as bob@acme → HTTP 200
{"detail":"run not found"} → HTTP 404
GET /runs as carol@globex → 0 runs
GET /conversations as bob@acme → ['In one sentence: what does a Postgres ad', 'In one sentence: what does a Postgres ad']
GET /conversations as carol@globex → []

$ the record stream follows the same rule
bob@acme stream events: 7
{"detail":"run not found"} → HTTP 404

$ memory: alice@acme stores a fact; bob@acme recalls it; carol@globex cannot
memory 2b14ba88-f8b8-4cb4-ba5a-1d4b69340a0c owner 21623525-0eb0-5f37-8bf2-e203d4223e13
bob@acme recall → ['the acme roadmap ships pgvector recall in Q4', 'the acme roadmap ships pgvector recall in Q4']
carol@globex recall → []

$ the default provider back (AUTH_PROVIDER unset): byte-identical single-user — no identity needed, no headers, the builtin's login answers 409 while dark
 Container concierge-agent-backend-1 Started 
ready after 6s on :8005
HTTP/1.1 200 OK
{"detail":"auth is disabled (AUTH_ENABLED=false)"} → HTTP 409
GET /runs/{id} with no identity → HTTP 200
# end — 2026-09-10T01:09:05Z
```
