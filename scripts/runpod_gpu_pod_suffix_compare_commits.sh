#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${ALLOW_RUNPOD_SUFFIX_COMPARE:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_SUFFIX_COMPARE=1" >&2
  echo "This script runs paid normal RunPod GPU Pod speed tests for two commits." >&2
  echo "Do not run it on 47.80.70.211 or on a production server." >&2
  exit 2
fi

BASE_COMMIT="${BASE_COMMIT:-f2a17c99f41d9e0069f474a087caa49c95f6fc5d}"
TEST_COMMIT="${TEST_COMMIT:-$(git rev-parse HEAD)}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
WORKDIR="${WORKDIR:-/tmp/tron-suffix-compare-$RUN_ID}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/suffix_compare_$RUN_ID}"

case "$BASE_COMMIT" in
  ""|*[!0-9a-f]*)
    echo "BASE_COMMIT must be a lowercase git commit hash" >&2
    exit 1
    ;;
esac
case "$TEST_COMMIT" in
  ""|*[!0-9a-f]*)
    echo "TEST_COMMIT must be a lowercase git commit hash" >&2
    exit 1
    ;;
esac

if [ "$BASE_COMMIT" = "$TEST_COMMIT" ]; then
  echo "BASE_COMMIT and TEST_COMMIT are identical; nothing to compare" >&2
  exit 1
fi
if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi

mkdir -p "$WORKDIR" "$RESULT_DIR"

echo "== RunPod suffix compare"
echo "base_commit=$BASE_COMMIT"
echo "test_commit=$TEST_COMMIT"
echo "run_id=$RUN_ID"
echo "workdir=$WORKDIR"
echo "result_dir=$RESULT_DIR"
echo "cuda_arch=${CUDA_ARCH:-sm_80}"
echo "benchmark_seconds=${BENCHMARK_SECONDS:-3}"
echo "sweep_step_sizes=${SWEEP_STEP_SIZES:-1024 2048 4096}"
echo "sweep_grids=${SWEEP_GRIDS:-8,128 16,128 32,128 64,128 128,128}"

run_one_commit() {
  local label="$1"
  local commit="$2"
  local clone_dir="$WORKDIR/$label"
  local label_result_dir="$RESULT_DIR/$label"

  echo "== clone $label $commit"
  git clone --quiet "$ROOT" "$clone_dir"
  git -C "$clone_dir" checkout --quiet "$commit"
  mkdir -p "$label_result_dir"

  echo "== run suffix speed test $label"
  (
    cd "$clone_dir"
    ALLOW_RUNPOD_SUFFIX_SPEED_TEST=1 \
    RUN_ID="${RUN_ID}_${label}" \
    RESULT_DIR="$label_result_dir" \
      scripts/runpod_gpu_pod_suffix_speed_test.sh
  ) 2>&1 | tee "$RESULT_DIR/${label}.stdout.txt"
}

run_one_commit "base" "$BASE_COMMIT"
run_one_commit "test" "$TEST_COMMIT"

python3 - "$RESULT_DIR" "$BASE_COMMIT" "$TEST_COMMIT" <<'PY'
from pathlib import Path
import json
import sys

result_dir = Path(sys.argv[1])
base_commit = sys.argv[2]
test_commit = sys.argv[3]

def load(label):
    inspect_path = result_dir / label / "speed_sweep_inspect.json"
    summary_path = result_dir / label / "speed_sweep_summary.json"
    if not inspect_path.exists():
        raise SystemExit(f"missing inspect result: {inspect_path}")
    data = json.loads(inspect_path.read_text())
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return {
        "commit": base_commit if label == "base" else test_commit,
        "inspect_path": str(inspect_path),
        "summary_path": str(summary_path),
        "decision": data.get("decision"),
        "best_step_size": data.get("best_step_size") or summary.get("best_step_size"),
        "best_grid": data.get("best_grid") or summary.get("best_grid"),
        "best_candidate_attempts_per_second_estimate": float(
            data.get("best_candidate_attempts_per_second_estimate")
            or summary.get("best_candidate_attempts_per_second_estimate")
            or 0.0
        ),
        "gpu_utilization": data.get("gpu_utilization") or summary.get("gpu_utilization"),
        "build_diagnostics": data.get("build_diagnostics"),
        "warnings": data.get("warnings", []),
        "failures": data.get("failures", []),
    }

base = load("base")
test = load("test")
base_speed = base["best_candidate_attempts_per_second_estimate"]
test_speed = test["best_candidate_attempts_per_second_estimate"]
delta = test_speed - base_speed
ratio = (test_speed / base_speed) if base_speed > 0 else None

result = {
    "mode": "suffix_commit_compare",
    "passed": bool(base_speed > 0 and test_speed > 0),
    "base": base,
    "test": test,
    "delta_candidate_attempts_per_second": delta,
    "speed_ratio_test_over_base": ratio,
    "notes": [
        "This compares two commits on the same normal RunPod GPU Pod with the same sweep settings.",
        "It is not Serverless proof and does not include age/find delivery.",
        "Use ptxas registers/spill and GPU utilization to interpret whether code changes helped or hurt.",
    ],
}
out = result_dir / "suffix_compare_summary.json"
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
PY

echo "suffix_compare_complete"
