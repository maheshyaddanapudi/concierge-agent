#!/usr/bin/env bash
# M55 §14r-97/98 on the shipped stack: the reference stub auth provider is
# selected by environment only (AUTH_PROVIDER=stub, AUTH_PROVIDER_MODULE=
# tests.auth_stub — the image ships its tests), a chat run on the live
# model, tenancy through the middleware, the stores, the streams and memory
# recall; then the default provider back, byte-identical. The backend is
# recreated with `docker compose` using the caller's COMPOSE_FILE / profile
# environment. Output: transcript on stdout.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$ACC_ROOT" || exit 1
as() { echo "-H X-Stub-User:$1 -H X-Stub-Tenant:$2 -H X-Stub-Role:${3:-member}"; }

echo "# M55 seam drill — $(date -u +%FT%TZ)"
say "AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub docker compose up -d --force-recreate backend"
AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub docker compose up -d --force-recreate backend 2>&1 | tail -1
API=$(api_root); wait_ready
docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -iE "auth_provider|UnknownAuthProvider" | tail -2 | cut -c1-160
say "no identity → 401 on the API; /health and /ready stay open"
curl -s -o /dev/null -w 'GET /tools (no headers) → HTTP %{http_code}\n' $API/tools
curl -s -o /dev/null -w 'GET /health → HTTP %{http_code}\n' ${API%/api/v1}/health
say "the builtin's login route is not offered by another provider"
curl -s -X POST $API/auth/login -H "$H" -d '{"username":"admin","password":"x"}' -w ' → HTTP %{http_code}\n'
say "writes need the stub's editor role: bob@acme (member) PATCH /settings → 403 with the stub's reason; alice@acme (editor) → 200"
curl -s -X PATCH $API/settings -H "$H" $(as bob acme) -d "{\"default_model\":\"$ACC_MODEL\"}" -w ' → HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" $(as alice acme editor) -d "{\"default_model\":\"$ACC_MODEL\",\"formatter_enabled\":false,\"memory_enabled\":true}" | py 'print({k:d[k] for k in ("default_model","memory_enabled")}, "→ HTTP 200")'
say "alice@acme starts a chat run on the live model"
RID=$(curl -s -X POST $API/chat -H "$H" $(as alice acme) -d '{"message":"In one sentence: what does a Postgres advisory lock guarantee?"}' | py 'print(d["run_id"])')
echo "run $RID"
for i in $(seq 1 120); do st=$(psql_ "select status from runs where id='$RID'"); case "$st" in completed|failed|cancelled) break;; esac; sleep 1; done
psql_ "select status, user_id, left(final_answer,110) from runs where id='$RID'"
echo "alice's id per the stub: $(docker exec "$ACC_BACKEND_CONTAINER" python -c 'from tests.auth_stub import user_id_for; print(user_id_for("alice"))')"
say "the run is bob@acme's to see (same tenant) and invisible to carol@globex"
curl -s $API/runs/$RID $(as bob acme) -o /dev/null -w 'GET /runs/{id} as bob@acme → HTTP %{http_code}\n'
curl -s $API/runs/$RID $(as carol globex) -w ' → HTTP %{http_code}\n'
curl -s "$API/runs?limit=50" $(as carol globex) | py 'print("GET /runs as carol@globex →", len(d) if isinstance(d,list) else d.get("items", d), "runs")'
curl -s $API/conversations $(as bob acme) | py 'print("GET /conversations as bob@acme →", [c["title"][:40] for c in d])'
curl -s $API/conversations $(as carol globex) | py 'print("GET /conversations as carol@globex →", d)'
say "the record stream follows the same rule"
curl -s -N --max-time 3 $API/chat/stream/$RID $(as bob acme) | grep -c "^event:" | sed 's/^/bob@acme stream events: /'
curl -s $API/chat/stream/$RID $(as carol globex) -w ' → HTTP %{http_code}\n' --max-time 3
say "memory: alice@acme stores a fact; bob@acme recalls it; carol@globex cannot"
MID=$(curl -s -X POST $API/memories -H "$H" $(as alice acme) -d '{"kind":"fact","text":"the acme roadmap ships pgvector recall in Q4","scope":"global"}' | py 'print(d["id"])')
echo "memory $MID owner $(psql_ "select user_id from memories where id='$MID'")"
curl -s "$API/memories/recall?q=acme+roadmap+pgvector" $(as bob acme) | py 'print("bob@acme recall →", [h["memory"]["text"][:50] for h in d])'
curl -s "$API/memories/recall?q=acme+roadmap+pgvector" $(as carol globex) | py 'print("carol@globex recall →", d)'
say "the default provider back (AUTH_PROVIDER unset): byte-identical single-user — no identity needed, no headers, the builtin's login answers 409 while dark"
docker compose up -d --force-recreate backend 2>&1 | tail -1; API=$(api_root); wait_ready
curl -s -o /dev/null -D - $API/tools | grep -iE "^HTTP|x-frame-options|x-content-type" | tr -d '\r'
curl -s -X POST $API/auth/login -H "$H" -d '{"username":"admin","password":"x"}' -w ' → HTTP %{http_code}\n'
curl -s $API/runs/$RID -o /dev/null -w 'GET /runs/{id} with no identity → HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" -d '{"memory_enabled":false}' -o /dev/null
echo "# end — $(date -u +%FT%TZ)"
