# M55 seam drill — 2026-09-10T21:28:54Z

$ AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub docker compose up -d --force-recreate backend
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000

$ no identity → 401 on the API; /health and /ready stay open
GET /tools (no headers) → HTTP 401
GET /health → HTTP 200

$ the builtin's login route is not offered by another provider
{"detail":"login is not offered by the active auth provider"} → HTTP 404

$ writes need the stub's editor role: bob@acme (member) PATCH /settings → 403 with the stub's reason; alice@acme (editor) → 200
{"detail":"stub: registry and settings writes need the editor role"} → HTTP 403
{'default_model': 'openrouter:qwen/qwen3.8-max', 'memory_enabled': True} → HTTP 200

$ alice@acme starts a chat run on the live model
run 8a235ea2-952d-48e5-b996-9a6f99668d4e
completed|21623525-0eb0-5f37-8bf2-e203d4223e13|A Postgres advisory lock guarantees mutual exclusion over an application-defined key — only the session(s) hol
alice's id per the stub: 21623525-0eb0-5f37-8bf2-e203d4223e13

$ the run is bob@acme's to see (same tenant) and invisible to carol@globex
GET /runs/{id} as bob@acme → HTTP 200
{"detail":"run not found"} → HTTP 404
GET /runs as carol@globex → 0 runs
GET /conversations as bob@acme → ['In one sentence: what does a Postgres ad']
GET /conversations as carol@globex → []

$ the record stream follows the same rule
bob@acme stream events: 8
{"detail":"run not found"} → HTTP 404

$ memory: alice@acme stores a fact; bob@acme recalls it; carol@globex cannot
memory bc0ef5f0-b25c-46bd-a28e-24a33ede429e owner 21623525-0eb0-5f37-8bf2-e203d4223e13
bob@acme recall → ['the acme roadmap ships pgvector recall in Q4']
carol@globex recall → []

$ the default provider back (AUTH_PROVIDER unset): byte-identical single-user — no identity needed, no headers, the builtin's login answers 409 while dark
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 5s at http://localhost:8000
HTTP/1.1 200 OK
{"detail":"auth is disabled (AUTH_ENABLED=false)"} → HTTP 409
GET /runs/{id} with no identity → HTTP 200
# end — 2026-09-10T21:29:21Z
