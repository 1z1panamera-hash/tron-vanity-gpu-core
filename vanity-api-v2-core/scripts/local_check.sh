#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-/private/tmp/vanity_api_v2_core_build}"
PATCHED_SOURCE="${PATCHED_SOURCE:-/private/tmp/vanity_api_v2_round53_patch_check}"
CXX="${CXX:-$(command -v clang++ || command -v g++)}"

"$ROOT/scripts/check_production_boundary.sh"
"$ROOT/scripts/check_round52_patch.sh"
"$ROOT/scripts/check_round53_worker_state_patch.sh"
bash -n "$ROOT/scripts/build_round52_v2_from_round51.sh"
bash -n "$ROOT/scripts/apply_round53_worker_state_patch.sh"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/private/tmp/vanity18035-core-pycache}" \
  python3 -m py_compile "$ROOT/scripts/vast_daemon_smoke.py"
if [ "$(uname -m)" = "x86_64" ]; then
  "$CXX" \
    -std=c++17 -Wall -Wextra -Werror -fsyntax-only \
    -I"$PATCHED_SOURCE" -I"$ROOT/include" \
    "$ROOT/tools/vanity18035_core_daemon.cpp"
elif [ "$(uname -s)" = "Darwin" ] && command -v clang++ >/dev/null 2>&1; then
  clang++ \
    -target x86_64-apple-macos13 -D__rdtsc=vanity_rdtsc \
    -std=c++17 -Wall -Wextra -Werror -fsyntax-only \
    -I"$PATCHED_SOURCE" -I"$ROOT/include" \
    "$ROOT/tools/vanity18035_core_daemon.cpp"
else
  test -s "$ROOT/tools/vanity18035_core_daemon.cpp"
fi
bash -n "$ROOT/scripts/run_gpu_pattern_matrix.sh"
test -s "$ROOT/tools/gpu_multi_target_benchmark.cpp"
test "$(wc -l < "$ROOT/tests/forced_hit_patterns.tsv" | tr -d ' ')" = "25"

if command -v cmake >/dev/null 2>&1; then
  cmake -S "$ROOT" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD_DIR" --parallel
  ctest --test-dir "$BUILD_DIR" --output-on-failure
else
  mkdir -p "$BUILD_DIR"
  "$CXX" \
    -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$ROOT/include" \
    "$ROOT/src/tron_pattern.cpp" \
    "$ROOT/tests/test_tron_pattern.cpp" \
    -o "$BUILD_DIR/test_tron_pattern"
  "$BUILD_DIR/test_tron_pattern"
  "$CXX" \
    -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$ROOT/include" \
    "$ROOT/src/worker_protocol.cpp" \
    "$ROOT/tests/test_worker_protocol.cpp" \
    -o "$BUILD_DIR/test_worker_protocol"
  "$BUILD_DIR/test_worker_protocol"
  "$CXX" \
    -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$ROOT/include" \
    "$ROOT/src/core_security.cpp" \
    "$ROOT/tests/test_core_security.cpp" \
    -o "$BUILD_DIR/test_core_security"
  "$BUILD_DIR/test_core_security"
  "$CXX" \
    -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$ROOT/include" \
    "$ROOT/src/worker_outbox.cpp" \
    "$ROOT/tests/test_worker_outbox.cpp" \
    -lsqlite3 \
    -o "$BUILD_DIR/test_worker_outbox"
  "$BUILD_DIR/test_worker_outbox"
fi

echo "vanity api v2 core local checks passed"
