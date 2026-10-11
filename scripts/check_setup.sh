#!/usr/bin/env bash
# CoMesh setup check (LANA-89).
#
# Answers the two questions that decide whether a fresh installation will work,
# without needing an API key and without writing anything:
#
#   1. Is the portal reachable, and under which address does it consider itself
#      reachable (APP_PUBLIC_URL / detected host)?
#   2. Which address would it derive for THIS caller?
#
# Usage:
#   scripts/check_setup.sh                      # defaults to http://localhost:8765
#   scripts/check_setup.sh http://portal-host:8765
#   PORTAL_URL=http://portal-host:8765 scripts/check_setup.sh
#
# Exit code 0 = the portal answered. A non-zero code plus the printed error is the
# actual finding — do not read "the command ran" as "the setup is fine".
set -u

PORTAL_URL="${1:-${PORTAL_URL:-http://localhost:8765}}"
PORTAL_URL="${PORTAL_URL%/}"

echo "CoMesh setup check"
echo "  portal: ${PORTAL_URL}"

code=$(curl -s -o /tmp/comesh_net_echo.json -w '%{http_code}' --max-time 15 "${PORTAL_URL}/net/echo" 2>/dev/null)
[ -z "$code" ] && code=000
if [ "$code" != "200" ]; then
  echo "  !! /net/echo returned HTTP ${code} — the portal is not reachable at this address."
  echo "     Check PORTAL_URL / that the container is up (docker compose ps) and that"
  echo "     this host can resolve the name you used."
  exit 1
fi

python3 - "$PORTAL_URL" <<'PY'
import json, sys
portal_url = sys.argv[1]
try:
    data = json.load(open("/tmp/comesh_net_echo.json"))
except Exception as e:
    print(f"  !! could not parse the response: {e}")
    sys.exit(1)

p, c = data.get("portal", {}), data.get("caller", {})
print("  portal reachable: yes")
print(f"    public URL      : {p.get('public_url') or '(unset — derived per request)'}")
print(f"    advertise host  : {p.get('advertise_host')}")
print(f"    detected IP     : {p.get('detected_ip')}")
print(f"    hostname        : {p.get('hostname')}")
print(f"  caller as seen by the portal")
print(f"    peer host       : {c.get('peer_host')}")
print(f"    x-forwarded-for : {c.get('x-forwarded-for') or '(none — no reverse proxy)'}")
print(f"    x-real-ip       : {c.get('x-real-ip') or '(none)'}")
derived = data.get("derived_node_url")
print(f"  node URL the portal would derive for this caller: {derived or '(none — private/loopback address)'}")

print()
print("  Reading:")
print("  * If `derived_node_url` is a private 192.168./10./172. address the agent")
print("    also sees, this caller can host a node that the portal dials directly.")
print("  * Behind NAT the peer address is not dialable: set ADVERTISE_HOST on the")
print("    node (a DNS or mDNS name such as mygpu.local, or a mesh-VPN name) so the")
print("    portal learns a usable address from the agent's heartbeat.")
print("  * The portal needs no fixed IP of its own. Nodes are addressed by node_url,")
print("    which the portal fills in from the first heartbeat when it is left empty.")
PY
rc=$?
echo
echo "  Next: node-agent/README.md -> Quickstart, or node-agent: python agent.py --check"
exit $rc
