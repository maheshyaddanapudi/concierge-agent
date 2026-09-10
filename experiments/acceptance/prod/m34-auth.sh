#!/usr/bin/env bash
# M34 / §18.8 — the builtin auth provider live (§14c-32): the backend is
# recreated with AUTH_ENABLED=1 (docker compose, the caller's COMPOSE_FILE /
# profile environment), the bootstrap admin's one-time password is read off
# the boot log, and the matrix runs through curl: dark gate + security
# headers, login, a member user, a real-model run under an identity, tenancy
# both ways on runs and routines, the fire token as the only auth on the
# routine-fire path. Then the UI stage (34-auth-builtin) runs with the admin
# and member credentials, and the backend goes back to auth off.
# Output: transcript on stdout; UI frames under ACC_SHOTS/34-auth-builtin.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$ACC_ROOT" || exit 1
ACC_SHOTS=${ACC_SHOTS:-$ACC_HERE/shots}

echo "# M34 builtin auth drill — $(date -u +%FT%TZ)"
say "AUTH_ENABLED=1 docker compose up -d --force-recreate backend"
AUTH_ENABLED=1 docker compose up -d --force-recreate backend 2>&1 | tail -1
API=$(api_root); wait_ready
ROOT=${API%/api/v1}
say "§1 dark gate: unauthenticated /runs → 401 with the security headers; /health open"
curl -s -o /dev/null -D - $API/runs | grep -iE "^HTTP|x-content-type-options|x-frame-options|referrer-policy" | tr -d '\r'
curl -s -o /dev/null -w 'GET /health → HTTP %{http_code}\n' $ROOT/health
say "§2 bootstrap admin: the one-time password printed exactly once in the boot log"
PW=$(docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a auth_bootstrap_admin | tail -1 | python3 -c "import sys,json,re; line=sys.stdin.read().strip(); m=re.search(r'\{.*\}', line); d=json.loads(m.group(0)) if m else {}; print(d.get('one_time_password',''))")
if [ -z "$PW" ]; then
  echo "no bootstrap line in this boot — the admin already exists from an earlier auth-on boot; pass ACC_AUTH_PASSWORD"
  PW=${ACC_AUTH_PASSWORD:-}
fi
echo "admin one-time password: ${PW:0:3}… (${#PW} chars)"
TOKEN=$(curl -s -X POST $API/auth/login -H "$H" -d "{\"username\":\"admin\",\"password\":\"$PW\"}" | py 'print(d.get("token",""))')
echo "login → bearer token ${#TOKEN} chars"
curl -s $API/auth/me -H "Authorization: Bearer $TOKEN" | py 'print("GET /auth/me →", d)'
say "§3 user admin: admin creates member 'mallory'; she logs in with her own credentials"
curl -s -X POST $API/auth/users -H "$H" -H "Authorization: Bearer $TOKEN" -d '{"username":"mallory","password":"mallory-pass-1","role":"member"}' -w ' → HTTP %{http_code}\n' | cut -c1-160
MTOKEN=$(curl -s -X POST $API/auth/login -H "$H" -d '{"username":"mallory","password":"mallory-pass-1"}' | py 'print(d.get("token",""))')
echo "mallory login → bearer token ${#MTOKEN} chars"
say "§4 a real-model run under admin's identity"
curl -s -X PATCH $API/settings -H "$H" -H "Authorization: Bearer $TOKEN" -d "{\"default_model\":\"$ACC_MODEL\",\"orchestrator_mode\":\"graph\"}" -o /dev/null
RID=$(curl -s -X POST $API/chat -H "$H" -H "Authorization: Bearer $TOKEN" -d '{"message":"In one sentence: what is a bearer token?"}' | py 'print(d["run_id"])')
for i in $(seq 1 180); do st=$(curl -s $API/runs/$RID -H "Authorization: Bearer $TOKEN" | py 'print(d.get("status",""))'); case "$st" in completed|failed|cancelled) break;; esac; sleep 1; done
curl -s $API/runs/$RID -H "Authorization: Bearer $TOKEN" | py 'print("run", d["status"], "|", (d.get("final_answer") or "")[:110])'
echo "owner per db: $(psql_ "select user_id from runs where id='$RID'")"
say "§5 tenancy both ways: mallory sees no admin runs; direct fetch 404"
curl -s "$API/runs?limit=50" -H "Authorization: Bearer $MTOKEN" | py 'print("mallory GET /runs →", len(d) if isinstance(d,list) else d, "runs")'
curl -s $API/runs/$RID -H "Authorization: Bearer $MTOKEN" -o /dev/null -w 'mallory GET /runs/{admin run} → HTTP %{http_code}\n'
say "§6 ambient ownership: mallory's routine, invisible to admin; the fire token is the only auth on the fire path"
curl -s -X PATCH $API/settings -H "$H" -H "Authorization: Bearer $TOKEN" -d '{"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}' -o /dev/null
RT=$(curl -s -X POST $API/routines -H "$H" -H "Authorization: Bearer $MTOKEN" -d '{"name":"mallory-ping","prompt":"Reply with exactly: pong","autonomy":"propose","triggers":[{"type":"webhook"}]}' | py 'print(d.get("id",""))')
echo "mallory routine $RT"
curl -s $API/routines -H "Authorization: Bearer $TOKEN" | py 'print("admin GET /routines →", [r["name"] for r in d])'
curl -s -X POST $API/routines/$RT/token -H "Authorization: Bearer $TOKEN" -o /dev/null -w 'admin mints a token for it → HTTP %{http_code}\n'
FT=$(curl -s -X POST $API/routines/$RT/token -H "Authorization: Bearer $MTOKEN" | py 'print(d.get("fire_token",""))')
curl -s -X POST $API/routines/$RT/fire -H "$H" -H "Authorization: Bearer amb_wrong" -d '{"text":"ping","payload":{}}' -o /dev/null -w 'fire with a wrong token → HTTP %{http_code}\n'
curl -s -X POST $API/routines/$RT/fire -H "$H" -H "Authorization: Bearer $FT" -d '{"text":"ping","payload":{}}' -w ' → HTTP %{http_code}\n'
for i in $(seq 1 90); do n=$(curl -s "$API/runs?routine_id=$RT" -H "Authorization: Bearer $MTOKEN" | py 'print(len(d) if isinstance(d,list) else 0)'); [ "$n" != "0" ] && break; sleep 2; done
curl -s "$API/runs?routine_id=$RT" -H "Authorization: Bearer $MTOKEN" | py 'print("mallory GET /runs?routine_id →", [(r["status"], (r.get("final_answer") or "")[:30]) for r in d])'
curl -s "$API/runs?routine_id=$RT" -H "Authorization: Bearer $TOKEN" | py 'print("admin GET /runs?routine_id →", d)'
say "§7 §14e-43: rate_limit_burst moves the 429 boundary (the bucket keys on the identified principal — dark auth passes through untouched)"
curl -s -X PATCH $API/settings -H "$H" -H "Authorization: Bearer $TOKEN" -d '{"rate_limit_burst":5,"rate_limit_per_s":1}' -o /dev/null -w 'PATCH {rate_limit_burst: 5, rate_limit_per_s: 1} → HTTP %{http_code}\n'
sleep 1
for i in $(seq 1 8); do printf 'GET /skills [%d] -> %s\n' $i "$(curl -s -o /dev/null -w '%{http_code}' $API/skills -H "Authorization: Bearer $MTOKEN")"; done
sleep 3
for i in $(seq 1 10); do code=$(curl -s -o /dev/null -w '%{http_code}' -X PATCH $API/settings -H "$H" -H "Authorization: Bearer $TOKEN" -d '{"rate_limit_burst":120,"rate_limit_per_s":10}'); [ "$code" = 200 ] && break; sleep 1.5; done
echo "PATCH {rate_limit_burst: 120, rate_limit_per_s: 10} (retried while throttled) → HTTP $code"
sleep 2
for i in $(seq 1 8); do printf 'GET /skills [%d] -> %s\n' $i "$(curl -s -o /dev/null -w '%{http_code}' $API/skills -H "Authorization: Bearer $MTOKEN")"; done
say "§8 the UI: the login gate, admin signed in, a run under identity, the member's empty Runs page"
ACC_BEARER=$TOKEN ACC_AUTH_PASSWORD=$PW ACC_MEMBER_PASSWORD=mallory-pass-1 ACC_SHOTS=$ACC_SHOTS node "$ACC_HERE/../run.mjs" "$ACC_HERE/../stages/34-auth-builtin.mjs" 2>&1 | grep -v "^\s*$" | tail -20
say "auth back off: docker compose up -d --force-recreate backend"
docker compose up -d --force-recreate backend 2>&1 | tail -1; API=$(api_root); wait_ready
curl -s -o /dev/null -w 'GET /runs with no identity → HTTP %{http_code}\n' $API/runs
echo "# end — $(date -u +%FT%TZ)"
