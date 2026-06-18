#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${ALLOW_RUNPOD_SUFFIX_AUTOTUNE:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_SUFFIX_AUTOTUNE=1" >&2
  echo "This script runs a paid normal RunPod GPU Pod speed autotune." >&2
  echo "Do not run it on 47.80.70.211 or on a production server." >&2
  exit 2
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi not found; run this only inside a GPU Pod" >&2
  exit 1
fi

GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/suffix_autotune_$RUN_ID}"
BENCHMARK_SECONDS="${BENCHMARK_SECONDS:-3}"

CUDA_ARCH_VALUE="${CUDA_ARCH:-}"
SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES:-}"
SWEEP_GRIDS_VALUE="${SWEEP_GRIDS:-}"
GPU_CLASS="generic"

case "$GPU_NAME" in
  *"RTX 3090"*)
    GPU_CLASS="rtx3090"
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_86}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-1024 2048 3072 4096}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-16,128 32,128 48,128 64,128 96,128}"
    ;;
  *"RTX 4090"*)
    GPU_CLASS="rtx4090"
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_89}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-2048 3072 4096 6144}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-32,128 64,128 96,128 128,128}"
    ;;
  *"RTX 5090"*|*"RTX PRO 6000"*|*"Blackwell"*)
    GPU_CLASS="blackwell"
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_120}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-2048 4096 6144 8192}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-64,128 96,128 128,128 160,128}"
    ;;
  *"H100"*|*"H200"*)
    GPU_CLASS="hopper"
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_90}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-2048 4096 6144 8192}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-32,128 64,128 96,128 128,128 160,128}"
    ;;
  *"A100"*)
    GPU_CLASS="a100"
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_80}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-1024 2048 4096}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-16,128 32,128 64,128 96,128}"
    ;;
  *)
    CUDA_ARCH_VALUE="${CUDA_ARCH_VALUE:-sm_80}"
    SWEEP_STEP_SIZES_VALUE="${SWEEP_STEP_SIZES_VALUE:-1024 2048 4096}"
    SWEEP_GRIDS_VALUE="${SWEEP_GRIDS_VALUE:-8,128 16,128 32,128 64,128 128,128}"
    ;;
esac

mkdir -p "$RESULT_DIR"

cat >"$RESULT_DIR/autotune_config.json" <<EOF
{
  "mode": "suffix_autotune_config",
  "repo_commit": "$(git rev-parse HEAD)",
  "gpu_name": "$GPU_NAME",
  "gpu_class": "$GPU_CLASS",
  "cuda_arch": "$CUDA_ARCH_VALUE",
  "cuda_archs": "$CUDA_ARCH_VALUE",
  "benchmark_seconds": $BENCHMARK_SECONDS,
  "sweep_step_sizes": "$SWEEP_STEP_SIZES_VALUE",
  "sweep_grids": "$SWEEP_GRIDS_VALUE",
  "notes": [
    "Autotune uses a single native CUDA architecture for fixed GPU Pods.",
    "This avoids fat-binary build overhead when testing 3090/4090/5090 dedicated Pods.",
    "No customer suffixes or private key material should be used."
  ]
}
EOF

echo "== RunPod suffix autotune"
cat "$RESULT_DIR/autotune_config.json"

ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1 \
RUN_ID="$RUN_ID" \
RESULT_DIR="$RESULT_DIR" \
CUDA_ARCH="$CUDA_ARCH_VALUE" \
CUDA_ARCHS="$CUDA_ARCH_VALUE" \
BENCHMARK_SECONDS="$BENCHMARK_SECONDS" \
SWEEP_STEP_SIZES="$SWEEP_STEP_SIZES_VALUE" \
SWEEP_GRIDS="$SWEEP_GRIDS_VALUE" \
  scripts/runpod_gpu_pod_suffix_speed_sweep.sh

scripts/inspect_suffix_speed_sweep.py "$RESULT_DIR" | tee "$RESULT_DIR/speed_sweep_inspect.json"

echo "suffix_autotune_complete"
