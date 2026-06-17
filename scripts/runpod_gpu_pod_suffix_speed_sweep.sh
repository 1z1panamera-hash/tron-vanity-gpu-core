#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_suffix_only_20260618.patch"
EXPECTED_PATCH_SHA="8dae0ae4ed3b8afd9bb93c6fd569a2aa4bf621d32f7330b49323662d14b2daa9"

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
SWEEP_STEP_SIZES="${SWEEP_STEP_SIZES:-1024 2048 4096}"
SWEEP_GRIDS="${SWEEP_GRIDS:-8,128 16,128 32,128 64,128 128,128}"
PROFILE_GRID="${PROFILE_GRID:-64,128}"
PROFILE_STEP_SIZE="${PROFILE_STEP_SIZE:-4096}"
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
case "$PROFILE_STEP_SIZE" in
  ''|*[!0-9]*)
    echo "PROFILE_STEP_SIZE must be an integer" >&2
    exit 1
    ;;
esac

if ! [[ "$BENCHMARK_PATTERN" =~ ^T\*[1-9A-HJ-NP-Za-km-z]{5}$ ]]; then
  echo "BENCHMARK_PATTERN must be suffix-only format T*<five-base58-chars>" >&2
  exit 1
fi

if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi

mkdir -p "$WORKDIR" "$RESULT_DIR"

GPU_UTIL_PID=""
stop_gpu_util_sampler() {
  if [ -n "${GPU_UTIL_PID:-}" ]; then
    kill "$GPU_UTIL_PID" 2>/dev/null || true
    wait "$GPU_UTIL_PID" 2>/dev/null || true
    GPU_UTIL_PID=""
  fi
}
trap stop_gpu_util_sampler EXIT

start_gpu_util_sampler() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "nvidia_smi_not_found" | tee "$RESULT_DIR/nvidia_smi_not_found.txt"
    return
  fi
  nvidia-smi >"$RESULT_DIR/nvidia_smi_initial.txt" 2>&1 || true
  nvidia-smi \
    --query-gpu=timestamp,index,name,driver_version,utilization.gpu,utilization.memory,power.draw,memory.used,memory.total \
    --format=csv \
    -l 1 \
    >"$RESULT_DIR/gpu_utilization.csv" 2>"$RESULT_DIR/gpu_utilization.stderr.txt" &
  GPU_UTIL_PID=$!
}

echo "== suffix speed sweep"
echo "repo_commit=$(git -C "$ROOT" rev-parse HEAD)"
echo "cuda_arch=$CUDA_ARCH_INPUT"
echo "ccap=$CCAP"
echo "benchmark_seconds=$BENCHMARK_SECONDS"
echo "benchmark_pattern=$BENCHMARK_PATTERN"
echo "sweep_step_sizes=$SWEEP_STEP_SIZES"
echo "sweep_grids=$SWEEP_GRIDS"
echo "profile_step_size=$PROFILE_STEP_SIZE"
echo "result_dir=$RESULT_DIR"
echo "engineering_min_attempts_per_second=200000000"
echo "engineering_preferred_attempts_per_second=300000000"

start_gpu_util_sampler

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

CURRENT_STEP_SIZE=""

build_step_size() {
  local step_size="$1"
  case "$step_size" in
    ''|*[!0-9]*)
      echo "STEP_SIZE must be an integer: $step_size" >&2
      exit 1
      ;;
  esac
  if [ $((step_size % 1024)) -ne 0 ]; then
    echo "STEP_SIZE must be a multiple of 1024 for this sweep: $step_size" >&2
    exit 1
  fi
  echo "== build VanitySearch STEP_SIZE=$step_size"
  make clean >/dev/null 2>&1 || true
  make gpu=1 CCAP="$CCAP" CUDA="$CUDA_HOME" CXXCUDA="$CXXCUDA" STEP_SIZE="$step_size" all \
    2>&1 | tee "$RESULT_DIR/build_step_${step_size}.stdout.txt"
  CURRENT_STEP_SIZE="$step_size"
}

run_benchmark_grid() {
  local step_size="$1"
  local grid="$2"
  local safe_grid="${grid//,/x}"
  local stdout_file="$RESULT_DIR/benchmark_step_${step_size}_grid_${safe_grid}.stdout.txt"
  local stderr_file="$RESULT_DIR/benchmark_step_${step_size}_grid_${safe_grid}.stderr.txt"
  local json_file="$RESULT_DIR/benchmark_step_${step_size}_grid_${safe_grid}.json"

  echo "== benchmark STEP_SIZE=$step_size grid=$grid"
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

  python3 - "$stdout_file" "$stderr_file" "$step_size" "$grid" "$BENCHMARK_SECONDS" "$rc" "$json_file" <<'PY'
from pathlib import Path
import json
import re
import sys

stdout_path, stderr_path, step_size, grid, seconds, rc, json_path = sys.argv[1:]
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
    "step_size": int(step_size),
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

for step_size in $SWEEP_STEP_SIZES; do
  build_step_size "$step_size"
  for grid in $SWEEP_GRIDS; do
    run_benchmark_grid "$step_size" "$grid"
  done
done

if [ "${RUN_NSYS:-0}" = "1" ]; then
  if command -v nsys >/dev/null 2>&1; then
    if [ "$CURRENT_STEP_SIZE" != "$PROFILE_STEP_SIZE" ]; then
      build_step_size "$PROFILE_STEP_SIZE"
    fi
    echo "== optional nsys profile STEP_SIZE=$PROFILE_STEP_SIZE grid=$PROFILE_GRID"
    env TRON_SUPPRESS_SECRET_OUTPUT=1 timeout "${PROFILE_SECONDS}s" \
      nsys profile --force-overwrite=true \
        -o "$RESULT_DIR/nsys_suffix_step_${PROFILE_STEP_SIZE}_grid_${PROFILE_GRID//,/x}" \
        ./VanitySearch -gpu -t 0 -g "$PROFILE_GRID" "$BENCHMARK_PATTERN" \
      >"$RESULT_DIR/nsys.stdout.txt" 2>"$RESULT_DIR/nsys.stderr.txt" || true
  else
    echo "nsys_not_found" | tee "$RESULT_DIR/nsys_not_found.txt"
  fi
fi

if [ "${RUN_NVPROF:-0}" = "1" ]; then
  if command -v nvprof >/dev/null 2>&1; then
    if [ "$CURRENT_STEP_SIZE" != "$PROFILE_STEP_SIZE" ]; then
      build_step_size "$PROFILE_STEP_SIZE"
    fi
    echo "== optional nvprof profile STEP_SIZE=$PROFILE_STEP_SIZE grid=$PROFILE_GRID"
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
util_path = result_dir / "gpu_utilization.csv"
gpu_utilization = {
    "path": str(util_path),
    "present": util_path.exists(),
    "samples": 0,
    "avg_gpu_utilization_percent": None,
    "max_gpu_utilization_percent": None,
}
if util_path.exists():
    import csv
    import re

    samples = []
    with util_path.open(newline="", errors="ignore") as handle:
        for row in csv.reader(handle):
            if not row or row[0].strip().lower() == "timestamp":
                continue
            if len(row) < 5:
                continue
            match = re.search(r"([0-9.]+)", row[4])
            if match:
                samples.append(float(match.group(1)))
    if samples:
        gpu_utilization = {
            "path": str(util_path),
            "present": True,
            "samples": len(samples),
            "avg_gpu_utilization_percent": sum(samples) / len(samples),
            "max_gpu_utilization_percent": max(samples),
        }
summary = {
    "mode": "suffix_speed_sweep_summary",
    "passed": bool(best and best_speed > 0),
    "result_dir": str(result_dir),
    "best_step_size": best.get("step_size") if best else None,
    "best_grid": best.get("gpu_grid") if best else None,
    "best_candidate_attempts_per_second_estimate": best_speed,
    "engineering_min_attempts_per_second": 200_000_000,
    "engineering_preferred_attempts_per_second": 300_000_000,
    "meets_engineering_minimum": best_speed >= 200_000_000,
    "meets_engineering_preferred": best_speed >= 300_000_000,
    "gpu_utilization": gpu_utilization,
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
