#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_suffix_only_20260618.patch"
EXPECTED_PATCH_SHA="eed696759855c331cbac7c68231b33b627511f2df0cb636df4e59befa5ee29a7"

if [ "${ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1" >&2
  echo "This script is intended only for a short-lived normal RunPod GPU Pod." >&2
  echo "Do not run it on 47.80.70.211 or on a production server." >&2
  exit 2
fi

if [ ! -f "$PATCH_PATH" ]; then
  echo "missing patch: $PATCH_PATH" >&2
  exit 1
fi

actual_sha="$(sha256sum "$PATCH_PATH" | awk '{print $1}')"
if [ "$actual_sha" != "$EXPECTED_PATCH_SHA" ]; then
  echo "patch sha256 mismatch" >&2
  echo "expected=$EXPECTED_PATCH_SHA" >&2
  echo "actual=$actual_sha" >&2
  exit 1
fi

VANITYSEARCH_REPO="${VANITYSEARCH_REPO:-https://github.com/JeanLucPons/VanitySearch.git}"
VANITYSEARCH_COMMIT="${VANITYSEARCH_COMMIT:-c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-tron-speed-sweep-$RUN_ID}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/suffix_speed_sweep_$RUN_ID}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CUDA_ARCH_INPUT="${CUDA_ARCH:-sm_80}"
CCAP="${CUDA_ARCH_INPUT#sm_}"
CXXCUDA="${CXXCUDA:-/usr/bin/g++}"
BENCHMARK_PATTERN="${BENCHMARK_PATTERN:-T*CDEFG}"
BENCHMARK_SECONDS="${BENCHMARK_SECONDS:-3}"
SWEEP_GRIDS="${SWEEP_GRIDS:-8,128 16,128 32,128 64,128 128,128}"
PROFILE_GRID="${PROFILE_GRID:-64,128}"
PROFILE_SECONDS="${PROFILE_SECONDS:-5}"

case "$BENCHMARK_SECONDS" in
  ''|*[!0-9]*)
    echo "BENCHMARK_SECONDS must be an integer" >&2
    exit 1
    ;;
esac
if [ "$BENCHMARK_SECONDS" -lt 3 ] || [ "$BENCHMARK_SECONDS" -gt 15 ]; then
  echo "BENCHMARK_SECONDS must be between 3 and 15 for speed sweep" >&2
  exit 1
fi

case "$PROFILE_SECONDS" in
  ''|*[!0-9]*)
    echo "PROFILE_SECONDS must be an integer" >&2
    exit 1
    ;;
esac
if [ "$PROFILE_SECONDS" -lt 3 ] || [ "$PROFILE_SECONDS" -gt 15 ]; then
  echo "PROFILE_SECONDS must be between 3 and 15" >&2
  exit 1
fi

if ! [[ "$BENCHMARK_PATTERN" =~ ^T\*[1-9A-HJ-NP-Za-km-z]{5}$ ]]; then
  echo "BENCHMARK_PATTERN must be suffix-only format T*<five-base58-chars>" >&2
  exit 1
fi

if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi

mkdir -p "$WORKDIR" "$RESULT_DIR"

echo "== suffix speed sweep"
echo "repo_commit=$(git -C "$ROOT" rev-parse HEAD)"
echo "cuda_arch=$CUDA_ARCH_INPUT"
echo "ccap=$CCAP"
echo "benchmark_seconds=$BENCHMARK_SECONDS"
echo "benchmark_pattern=$BENCHMARK_PATTERN"
echo "sweep_grids=$SWEEP_GRIDS"
echo "result_dir=$RESULT_DIR"

echo "== clone VanitySearch candidate base"
git clone --quiet "$VANITYSEARCH_REPO" "$WORKDIR/VanitySearch"
cd "$WORKDIR/VanitySearch"
git checkout --quiet "$VANITYSEARCH_COMMIT"

echo "== apply TRON suffix-only patch"
git apply "$PATCH_PATH"

echo "== vector gate"
CUDA_ARCH="$CUDA_ARCH_INPUT" scripts/runpod_verify_tron_gpu_address_layer.sh \
  | tee "$RESULT_DIR/vector_gate.stdout.txt"
if ! grep -q "tron_gpu_address_layer_passed" "$RESULT_DIR/vector_gate.stdout.txt"; then
  echo "vector gate failed" >&2
  exit 1
fi

echo "== build VanitySearch once"
make gpu=1 CCAP="$CCAP" CUDA="$CUDA_HOME" CXXCUDA="$CXXCUDA" all \
  2>&1 | tee "$RESULT_DIR/build.stdout.txt"

run_benchmark_grid() {
  local grid="$1"
  local safe_grid="${grid//,/x}"
  local stdout_file="$RESULT_DIR/benchmark_${safe_grid}.stdout.txt"
  local stderr_file="$RESULT_DIR/benchmark_${safe_grid}.stderr.txt"
  local json_file="$RESULT_DIR/benchmark_${safe_grid}.json"

  echo "== benchmark grid=$grid"
  local cmd=(env TRON_SUPPRESS_SECRET_OUTPUT=1 timeout "${BENCHMARK_SECONDS}s" ./VanitySearch -gpu -t 0 -g "$grid" "$BENCHMARK_PATTERN")
  set +e
  if command -v script >/dev/null 2>&1; then
    printf -v shell_cmd "%q " "${cmd[@]}"
    script -q -e -c "$shell_cmd" "$stdout_file" >/dev/null 2>"$stderr_file"
  else
    "${cmd[@]}" >"$stdout_file" 2>"$stderr_file"
  fi
  local rc=$?
  set -e

  if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
    echo "benchmark failed grid=$grid rc=$rc" >&2
    tail -80 "$stdout_file" >&2 || true
    tail -80 "$stderr_file" >&2 || true
    exit 1
  fi

  if grep -Eiq "Priv|WIF|HEX|private_key|mnemonic|seed|token|secret" "$stdout_file" "$stderr_file"; then
    echo "unexpected sensitive marker or hit output in benchmark grid=$grid" >&2
    exit 1
  fi

  python3 - "$stdout_file" "$stderr_file" "$grid" "$BENCHMARK_SECONDS" "$rc" "$json_file" <<'PY'
from pathlib import Path
import json
import re
import sys

stdout_path, stderr_path, grid, seconds, rc, json_path = sys.argv[1:]
stdout = Path(stdout_path).read_text(errors="ignore")
stderr = Path(stderr_path).read_text(errors="ignore")
matches = re.findall(r"\[([0-9.]+) Mkey/s\]\[GPU ([0-9.]+) Mkey/s\]", stdout)
if matches:
    total_mkey_s, gpu_mkey_s = (float(value) for value in matches[-1])
    speed = gpu_mkey_s * 1_000_000.0
    passed = True
    error = None
else:
    total_mkey_s = None
    gpu_mkey_s = None
    speed = 0.0
    passed = False
    error = "no Mkey/s sample found"

result = {
    "mode": "suffix_speed_sweep_grid",
    "passed": passed,
    "error": error,
    "gpu_grid": grid,
    "duration_seconds_limit": int(seconds),
    "return_code": int(rc),
    "timeout_reached": int(rc) == 124,
    "samples": len(matches),
    "reported_total_mkey_s": total_mkey_s,
    "reported_gpu_mkey_s": gpu_mkey_s,
    "candidate_attempts_per_second_estimate": speed,
    "stderr_tail": stderr[-1200:],
}
Path(json_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, sort_keys=True))
if not passed:
    raise SystemExit(1)
PY
}

for grid in $SWEEP_GRIDS; do
  run_benchmark_grid "$grid"
done

if [ "${RUN_NSYS:-0}" = "1" ]; then
  if command -v nsys >/dev/null 2>&1; then
    echo "== optional nsys profile grid=$PROFILE_GRID"
    env TRON_SUPPRESS_SECRET_OUTPUT=1 timeout "${PROFILE_SECONDS}s" \
      nsys profile --force-overwrite=true \
        -o "$RESULT_DIR/nsys_suffix_${PROFILE_GRID//,/x}" \
        ./VanitySearch -gpu -t 0 -g "$PROFILE_GRID" "$BENCHMARK_PATTERN" \
      >"$RESULT_DIR/nsys.stdout.txt" 2>"$RESULT_DIR/nsys.stderr.txt" || true
  else
    echo "nsys_not_found" | tee "$RESULT_DIR/nsys_not_found.txt"
  fi
fi

if [ "${RUN_NVPROF:-0}" = "1" ]; then
  if command -v nvprof >/dev/null 2>&1; then
    echo "== optional nvprof profile grid=$PROFILE_GRID"
    env TRON_SUPPRESS_SECRET_OUTPUT=1 timeout "${PROFILE_SECONDS}s" \
      nvprof ./VanitySearch -gpu -t 0 -g "$PROFILE_GRID" "$BENCHMARK_PATTERN" \
      >"$RESULT_DIR/nvprof.stdout.txt" 2>"$RESULT_DIR/nvprof.stderr.txt" || true
  else
    echo "nvprof_not_found" | tee "$RESULT_DIR/nvprof_not_found.txt"
  fi
fi

python3 - "$RESULT_DIR" <<'PY'
from pathlib import Path
import json
import sys

result_dir = Path(sys.argv[1])
grid_results = []
for path in sorted(result_dir.glob("benchmark_*.json")):
    data = json.loads(path.read_text())
    grid_results.append(data)

best = max(
    grid_results,
    key=lambda item: float(item.get("candidate_attempts_per_second_estimate") or 0.0),
    default=None,
)
best_speed = float(best.get("candidate_attempts_per_second_estimate") or 0.0) if best else 0.0
summary = {
    "mode": "suffix_speed_sweep_summary",
    "passed": bool(best and best_speed > 0),
    "result_dir": str(result_dir),
    "best_grid": best.get("gpu_grid") if best else None,
    "best_candidate_attempts_per_second_estimate": best_speed,
    "target_stage1_min": 50_000_000,
    "target_stage1_high": 100_000_000,
    "target_stage2": 200_000_000,
    "meets_stage1_min": best_speed >= 50_000_000,
    "meets_stage1_high": best_speed >= 100_000_000,
    "meets_stage2": best_speed >= 200_000_000,
    "grids": grid_results,
    "notes": [
        "This is a normal RunPod GPU Pod speed sweep, not Serverless proof.",
        "Age/find delivery work is intentionally paused during this speed sprint.",
        "Use profiler output to decide whether secp256k1 point walking, checksum/Base58, or launch/grid sizing is the bottleneck.",
    ],
}
out = result_dir / "speed_sweep_summary.json"
out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

echo "suffix_speed_sweep_complete"
