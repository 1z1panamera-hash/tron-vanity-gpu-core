#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/private/tmp/vanity18035-pycache}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON" "$ROOT/scripts/check_spec_lock.py"
"$PYTHON" "$ROOT/scripts/check_boundary.py"
"$PYTHON" -m compileall -q "$ROOT/src" "$ROOT/tests" "$ROOT/scripts"
"$PYTHON" -m unittest discover -s "$ROOT/tests" -t "$ROOT" -v
