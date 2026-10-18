#!/usr/bin/env bash
# End-to-end smoke check for the admin endpoints against a RUNNING portal.
#
#   bash scripts/smoke_admin.sh http://127.0.0.1:8799 "$ADMIN_API_KEY"
#
# Exercises the real HTTP surface (headers, status codes, idempotency replay)
# rather than the in-process TestClient. Exits non-zero on the first failure.
set -euo pipefail

BASE="${1:-http://127.0.0.1:8765}"
KEY="${2:-${ADMIN_API_KEY:?ADMIN_API_KEY muss gesetzt sein}}"
AH="Authorization: Bearer ${KEY}"

say() { printf '\n== %s\n' "$1"; }
ok()  { printf '   ok: %s\n' "$1"; }
die() { printf '   FAIL: %s\n' "$1" >&2; exit 1; }

code() { curl -s -o /tmp/smoke_body.json -w '%{http_code}' -m 15 "$@"; }
body() { cat /tmp/smoke_body.json; }

[ -n "$KEY" ] || die "no admin key given"

say "anonymous access is rejected"
[ "$(code "$BASE/admin/whoami")" = "401" ] || die "expected 401 without a key, got $(body)"
ok "401 without credentials"

say "admin identity"
[ "$(code -H "$AH" "$BASE/admin/whoami")" = "200" ] || die "whoami failed: $(body)"
ok "$(body)"

say "overview"
[ "$(code -H "$AH" "$BASE/admin/overview")" = "200" ] || die "overview failed: $(body)"
python3 - <<'PY'
import json
d = json.load(open('/tmp/smoke_body.json'))
assert d['nodes_total'] == d['nodes_online'] + d['nodes_offline'] + d['nodes_disabled'], d
print(f"   ok: {d['users_total']} users, {d['nodes_total']} nodes "
      f"({d['nodes_online']} online / {d['nodes_offline']} offline / {d['nodes_disabled']} disabled)")
PY

say "idempotent user creation"
EMAIL="smoke-$$@example.com"
IK="smoke-create-$$"
[ "$(code -X POST -H "$AH" -H 'Content-Type: application/json' -H "Idempotency-Key: $IK" \
      -d "{\"email\":\"$EMAIL\",\"name\":\"Smoke User\",\"initial_credits\":7}" "$BASE/admin/users")" = "201" ] \
  || die "create failed: $(body)"
UID_=$(python3 -c 'import json;print(json.load(open("/tmp/smoke_body.json"))["user_id"])')
ok "created user $UID_"

code -X POST -H "$AH" -H 'Content-Type: application/json' -H "Idempotency-Key: $IK" \
     -d "{\"email\":\"$EMAIL\",\"name\":\"Smoke User\",\"initial_credits\":7}" "$BASE/admin/users" >/dev/null
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
assert d["replayed"] is True and d["api_key"] is None, d
print("   ok: replay returned the stored result, no second key")'

say "idempotent topup"
TK="smoke-topup-$$"
for i in 1 2; do
  code -X POST -H "$AH" -H 'Content-Type: application/json' -H "Idempotency-Key: $TK" \
       -d '{"amount":12.5,"reason":"smoke"}' "$BASE/admin/users/$UID_/topup" >/dev/null
done
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
assert d["replayed"] is True and abs(d["credits"] - 19.5) < 1e-9, d
print("   ok: balance {} after two identical calls".format(d["credits"]))'

say "user listing includes the new user"
[ "$(code -H "$AH" "$BASE/admin/users?q=$EMAIL")" = "200" ] || die "list failed: $(body)"
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
assert d["total"] == 1, d
print("   ok: exactly one user matches, listed with credits/role:",
      {k: d["users"][0][k] for k in ("role", "is_active", "credits")})'

say "nodes: every node, offline included"
[ "$(code -H "$AH" "$BASE/admin/nodes?limit=200")" = "200" ] || die "node list failed: $(body)"
python3 - <<'PY'
import json
d = json.load(open('/tmp/smoke_body.json'))
print(f"   ok: {d['total']} nodes match, summary={d['summary']}")
for n in d['nodes'][:10]:
    print(f"      #{n['id']} {n['name'][:34]:34s} {n['effective_status']:9s} "
          f"raw={n['status']:8s} enabled={n['is_enabled']} ws={n['connection_state']}")
PY

say "an offline node is visible to the admin but hidden from the public list"
# Register a node for a normal user, heartbeat it offline, then look at it from
# both surfaces: /nodes/list hides it, /admin/nodes shows it.
code -X POST -H "$AH" -H 'Content-Type: application/json' \
     -d '{"email":"plain@example.com","name":"Plain User","initial_credits":5,"password":"pw12345"}' \
     "$BASE/admin/users" >/dev/null
PLAIN_KEY=$(curl -s -m 15 -X POST -H 'Content-Type: application/json' \
  -d '{"email":"plain@example.com","password":"pw12345"}' "$BASE/auth/login" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["api_key"])')

code -X POST -H "Authorization: Bearer $PLAIN_KEY" -H 'Content-Type: application/json' \
     -d '{"name":"smoke-offline-node","gpu_type":"Test GPU","vram_gb":24,"port":11434}' \
     "$BASE/nodes/register" >/dev/null
NODE_ID=$(python3 -c 'import json;print(json.load(open("/tmp/smoke_body.json"))["id"])')
NODE_AGENT_KEY=$(python3 -c 'import json;print(json.load(open("/tmp/smoke_body.json"))["agent_api_key"])')
OWNER_ID=$(python3 -c 'import json;print(json.load(open("/tmp/smoke_body.json"))["owner_id"])')
code -X POST -H "X-Node-Key: $NODE_AGENT_KEY" -H 'Content-Type: application/json' \
     -d '{"status":"offline","gpu_util":0.0,"vram_used_gb":0.0}' \
     "$BASE/nodes/$NODE_ID/heartbeat" >/dev/null

code -H "$AH" "$BASE/admin/nodes?q=smoke-offline-node" >/dev/null
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
n = d["nodes"][0]
assert n["effective_status"] == "offline" and n["online"] is False, n
print("   ok: admin sees node #{} as {}".format(n["id"], n["effective_status"]))'

code "$BASE/nodes/list?only_online=true" >/dev/null
python3 -c '
import json
ids = [n["id"] for n in json.load(open("/tmp/smoke_body.json"))]
assert '"$NODE_ID"' not in ids, ids
print("   ok: the same node is absent from the public /nodes/list")'

say "admin can pause another user's node (status becomes 'disabled')"
DKEY="smoke-disable-$$"
for i in 1 2; do
  code -X POST -H "$AH" -H "Idempotency-Key: $DKEY" \
       "$BASE/admin/users/$OWNER_ID/nodes/$NODE_ID/enable?enabled=false" >/dev/null
done
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
assert d["is_enabled"] is False and d["replayed"] is True and d["effective_status"] == "disabled", d
print("   ok: second call replayed, effective_status={}".format(d["effective_status"]))'

code -H "$AH" "$BASE/admin/nodes/$NODE_ID" >/dev/null
python3 -c '
import json
d = json.load(open("/tmp/smoke_body.json"))
assert d["effective_status"] == "disabled" and d["owner_email"] == "plain@example.com", d
print("   ok: node detail -> status={} owner={} heartbeats_24h={} ws={}".format(
    d["effective_status"], d["owner_email"], d["heartbeats_24h"], d["connection_state"]))'

say "all done"
