#!/usr/bin/env bash
# Local smoke-run of the GPU-Pool portal against a throwaway SQLite DB.
# Usage: scripts/smoke_run.sh [port]
set -euo pipefail
PORT="${1:-8799}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export DATA_DIR="${DATA_DIR:-$(mktemp -d /tmp/gpu-pool-smoke-XXXXXX)}"
export SEED_KEY_PATH="${SEED_KEY_PATH:-$DATA_DIR/seed_api_key.txt}"
# SEC-10: kein default-admin-schluessel. Ein fester Bearer in einem Skript, das in echte
# Deployments kopiert wird, ist ein offenes Tor mit bekanntem Riegel.
: "${ADMIN_API_KEY:?ADMIN_API_KEY muss gesetzt sein (scripts/generate_admin_key.sh)"}
export ADMIN_API_KEY
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@smoke.local}"
cd "$REPO"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --workers 1
