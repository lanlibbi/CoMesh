#!/usr/bin/env bash
# Local smoke-run of the GPU-Pool portal against a throwaway SQLite DB.
# Usage: scripts/smoke_run.sh [port]
set -euo pipefail
PORT="${1:-8799}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export DATA_DIR="${DATA_DIR:-$(mktemp -d /tmp/gpu-pool-smoke-XXXXXX)}"
export SEED_KEY_PATH="${SEED_KEY_PATH:-$DATA_DIR/seed_api_key.txt}"
export ADMIN_API_KEY="${ADMIN_API_KEY:-gpu_smoke_admin_key_0001}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@smoke.local}"
cd "$REPO"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --workers 1
