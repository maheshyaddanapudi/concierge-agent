# M34 builtin auth drill — 2026-09-10T20:45:34Z

$ ACC_RESET_ADMIN=1: dropping the bootstrap admin and the drill's member so the boot re-issues the one-time password
DELETE 1
DELETE 1

$ AUTH_ENABLED=1 docker compose up -d --force-recreate backend
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 6s at http://localhost:8006

$ §1 dark gate: unauthenticated /runs → 401 with the security headers; /health open
HTTP/1.1 401 Unauthorized
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: no-referrer
GET /health → HTTP 200

$ §2 bootstrap admin: the one-time password printed exactly once in the boot log
admin one-time password: 2wC… (16 chars)
login → bearer token 43 chars
GET /auth/me → {'id': 'f6072205-d49b-44e3-ae92-5a37739dfbe4', 'username': 'admin', 'role': 'admin', 'prefs': {}}

$ §3 user admin: admin creates member 'mallory'; she logs in with her own credentials
{"id":"44672543-0099-4761-9eee-42c7b9d315f3","username":"mallory","role":"member"} → HTTP 201
mallory login → bearer token 43 chars

$ §4 a real-model run under admin's identity
run completed | A bearer token is a type of access token that grants its holder (the "bearer") access to a protected resource 
owner per db: f6072205-d49b-44e3-ae92-5a37739dfbe4

$ §5 tenancy both ways: mallory sees no admin runs; direct fetch 404
mallory GET /runs → 0 runs
mallory GET /runs/{admin run} → HTTP 404

$ §6 ambient ownership: mallory's routine, invisible to admin; the fire token is the only auth on the fire path
mallory routine f493c3ed-4428-4318-833a-f5f8f428e36d
admin GET /routines → []
admin mints a token for it → HTTP 404
fire with a wrong token → HTTP 401
{"status":"accepted","event_id":"dbf087d0-a492-4e3a-9557-eac019ae3f8c"} → HTTP 202
mallory GET /runs?routine_id → [('running', '')]
admin GET /runs?routine_id → []

$ §7 §14e-43: rate_limit_burst moves the 429 boundary (the bucket keys on the identified principal — dark auth passes through untouched)
PATCH {rate_limit_burst: 5, rate_limit_per_s: 1} → HTTP 200
GET /skills [1] -> 200
GET /skills [2] -> 200
GET /skills [3] -> 200
GET /skills [4] -> 200
GET /skills [5] -> 200
GET /skills [6] -> 429
GET /skills [7] -> 429
GET /skills [8] -> 429
PATCH {rate_limit_burst: 120, rate_limit_per_s: 10} (retried while throttled) → HTTP 200
GET /skills [1] -> 200
GET /skills [2] -> 200
GET /skills [3] -> 200
GET /skills [4] -> 200
GET /skills [5] -> 200
GET /skills [6] -> 200
GET /skills [7] -> 200
GET /skills [8] -> 200

$ §8 the UI: the login gate, admin signed in, a run under identity, the member's empty Runs page
[   0.0s] # 34-auth-builtin — 2026-09-10T20:46:03.785Z
[   1.9s] shot 00-login-gate.png
[   3.6s] signed in: token in localStorage=true; me={"id":"f6072205-d49b-44e3-ae92-5a37739dfbe4","username":"admin","role":"admin","prefs":{}}
[   5.3s] shot 01-signed-in-admin.png
[   7.4s] UI send: In one sentence: what does a login gate protect?
[  18.7s] run 719fcbbc-363d-4034-bc65-9acae12e5f94 → completed after 9s
[  18.7s] run 719fcbbc-363d-4034-bc65-9acae12e5f94 → completed after 0s
[  19.9s] run 719fcbbc → completed; steps: plan::completed
[  19.9s] answer: A login gate protects access to whatever lies behind it — an app, account, API, or set of data — by requiring a user to prove their identity (e.g., credentials 
[  19.9s] run under admin: completed
[  20.1s] shot 02-run-under-identity.png
[  23.6s] mallory's Runs page rows: 1 (admin's run is invisible to her)
[  23.8s] shot 03-member-empty-runs.png (member context)
[  23.8s] # end — 2026-09-10T20:46:27.564Z

$ auth back off: docker compose up -d --force-recreate backend
 Container concierge-agent-backend-1 Started 
backend /ready 200 after 6s at http://localhost:8007
GET /runs with no identity → HTTP 200
# end — 2026-09-10T20:46:35Z
