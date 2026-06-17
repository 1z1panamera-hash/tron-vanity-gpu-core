#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${ALLOW_RUNPOD_SUFFIX_SPEED_TEST:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_SUFFIX_SPEED_TEST=1" >&2
  echo "This script runs a paid normal RunPod GPU Pod speed test." >&2
  echo "Do not run it on 47.80.70.211 or on a production server." >&2
  exit 2
fi

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/suffix_speed_sweep_$RUN_ID}"

echo "== RunPod suffix speed test"
echo "repo_commit=$(git rev-parse HEAD)"
echo "run_id=$RUN_ID"
echo "result_dir=$RESULT_DIR"
echo "cuda_arch=${CUDA_ARCH:-sm_80}"
echo "benchmark_seconds=${BENCHMARK_SECONDS:-3}"
echo "sweep_step_sizes=${SWEEP_STEP_SIZES:-1024 2048 4096}"
echo "sweep_grids=${SWEEP_GRIDS:-8,128 16,128 32,128 64,128 128,128}"

ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1 \
RUN_ID="$RUN_ID" \
RESULT_DIR="$RESULT_DIR" \
  scripts/runpod_gpu_pod_suffix_speed_sweep.sh

echo "== inspect suffix speed sweep result"
scripts/inspect_suffix_speed_sweep.py "$RESULT_DIR" | tee "$RESULT_DIR/speed_sweep_inspect.json"

echo "suffix_speed_test_complete"
