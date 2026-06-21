#!/usr/bin/env bash
set -euo pipefail

export ALLOW_GPU_FIND="${ALLOW_GPU_FIND:-1}"
export GPU_WORKER_BACKEND="${GPU_WORKER_BACKEND:-vanitysearch}"
export VAST_MODEL_SERVER_HOST="${VAST_MODEL_SERVER_HOST:-127.0.0.1}"
export VAST_MODEL_SERVER_PORT="${VAST_MODEL_SERVER_PORT:-18000}"
export VAST_MODEL_LOG_FILE="${VAST_MODEL_LOG_FILE:-/var/log/tron-vanity/model.log}"

mkdir -p "$(dirname "$VAST_MODEL_LOG_FILE")"
: > "$VAST_MODEL_LOG_FILE"

python3 -u /app/vast_model_server.py &
backend_pid="$!"

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT

python3 - <<'PY'
import os
import socket
import sys
import time

host = os.environ["VAST_MODEL_SERVER_HOST"]
port = int(os.environ["VAST_MODEL_SERVER_PORT"])
deadline = time.time() + 30
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1):
            sys.exit(0)
    except OSError:
        time.sleep(0.25)
raise SystemExit("Vast model backend did not become ready")
PY

set +e
python3 -u /app/worker.py 2>&1 | tee -a "$VAST_MODEL_LOG_FILE"
worker_rc="${PIPESTATUS[0]}"
set -e
exit "$worker_rc"
