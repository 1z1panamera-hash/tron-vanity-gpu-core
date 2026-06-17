#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CUDA_ARCH="${CUDA_ARCH:-sm_80}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/$RUN_ID}"
mkdir -p "$RESULT_DIR"

echo "== RunPod GPU Pod sequence"
echo "repo_commit=$(git rev-parse HEAD)"
echo "cuda_arch=$CUDA_ARCH"
echo "result_dir=$RESULT_DIR"

run_and_capture() {
  local name="$1"
  shift
  echo "== $name"
  "$@" 2>&1 | tee "$RESULT_DIR/${name}.stdout.txt"
}

require_marker() {
  local file="$1"
  local marker="$2"
  if ! grep -q "$marker" "$file"; then
    echo "missing required marker '$marker' in $file" >&2
    exit 1
  fi
}

inspect_benchmark() {
  local name="$1"
  local stdout_file="$RESULT_DIR/${name}.stdout.txt"
  local inspect_file="$RESULT_DIR/${name}.inspect.json"
  scripts/inspect_vanitysearch_benchmark.py "$stdout_file" | tee "$inspect_file"
}

run_and_capture vector_gate env \
  ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 \
  CUDA_ARCH="$CUDA_ARCH" \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh

VECTOR_STDOUT="$RESULT_DIR/vector_gate.stdout.txt"
require_marker "$VECTOR_STDOUT" "tron_gpu_address_layer_passed"
require_marker "$VECTOR_STDOUT" "tron_gpu_address_layer_script_passed"
require_marker "$VECTOR_STDOUT" "tron_gpu_vector_fields_verified"

if [ "${RUN_SMOKE:-0}" != "1" ]; then
  echo "sequence_stop_after_vector_gate"
  echo "Set RUN_SMOKE=1 to run the short startup smoke."
  exit 0
fi

run_and_capture smoke env \
  ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 \
  RUN_TRON_PATTERN_SMOKE=1 \
  CUDA_ARCH="$CUDA_ARCH" \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh

require_marker "$RESULT_DIR/smoke.stdout.txt" "tron_gpu_pattern_smoke_passed"

if [ "${RUN_BENCHMARK_3:-0}" != "1" ]; then
  echo "sequence_stop_after_smoke"
  echo "Set RUN_BENCHMARK_3=1 to run the 3 second bounded benchmark."
  exit 0
fi

run_and_capture benchmark_3s env \
  ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 \
  RUN_TRON_PATTERN_BENCHMARK=1 \
  BENCHMARK_SECONDS=3 \
  CUDA_ARCH="$CUDA_ARCH" \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh

require_marker "$RESULT_DIR/benchmark_3s.stdout.txt" "tron_gpu_pattern_benchmark_passed"
inspect_benchmark benchmark_3s

if [ "${RUN_BENCHMARK_10:-0}" != "1" ]; then
  echo "sequence_stop_after_benchmark_3s"
  echo "Set RUN_BENCHMARK_10=1 to run the 10 second bounded benchmark."
  exit 0
fi

run_and_capture benchmark_10s env \
  ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1 \
  RUN_TRON_PATTERN_BENCHMARK=1 \
  BENCHMARK_SECONDS=10 \
  CUDA_ARCH="$CUDA_ARCH" \
  scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh

require_marker "$RESULT_DIR/benchmark_10s.stdout.txt" "tron_gpu_pattern_benchmark_passed"
inspect_benchmark benchmark_10s

echo "sequence_complete"
