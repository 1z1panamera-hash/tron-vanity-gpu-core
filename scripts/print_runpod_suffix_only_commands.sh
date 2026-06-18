#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMMIT="$(git rev-parse HEAD)"
CUDA_ARCH_VALUE="${CUDA_ARCH:-sm_80}"

cat <<EOF
# TRON suffix-only RunPod GPU Pod commands
#
# This file only prints commands. It does not call RunPod, build Docker, or run CUDA.
# Current repo commit:
#   $COMMIT
#
# Product rule:
#   suffix-only last 5 Base58Check characters
#   prefix_len=0 suffix_len=5
#   search_space=58^5
#   target: mean <= 5s, P90 <= 8s
#
# Safety:
#   Do not run on 47.80.70.211.
#   Do not use customer suffixes.
#   Speed gate has passed; next Serverless work must use only test recipients and no customer data.
#   Verify age-encrypted find output before any customer use.

## 0. Clone on a normal RunPod GPU Pod
git clone https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git
cd tron-vanity-gpu-core
git rev-parse HEAD

## 1. Vector gate only
CUDA_ARCH=$CUDA_ARCH_VALUE scripts/runpod_gpu_pod_sequence.sh

## 2. If vector gate passes, run startup smoke
RUN_SMOKE=1 CUDA_ARCH=$CUDA_ARCH_VALUE scripts/runpod_gpu_pod_sequence.sh

## 3. If smoke passes, run 3 second bounded benchmark
RUN_SMOKE=1 RUN_BENCHMARK_3=1 CUDA_ARCH=$CUDA_ARCH_VALUE scripts/runpod_gpu_pod_sequence.sh

## 4. If 3 second benchmark is clean, run 10 second bounded benchmark
RUN_SMOKE=1 RUN_BENCHMARK_3=1 RUN_BENCHMARK_10=1 CUDA_ARCH=$CUDA_ARCH_VALUE scripts/runpod_gpu_pod_sequence.sh

## 5. Inspect latest saved result directory
latest_result_dir=\$(ls -dt runpod_results/* | head -1)
scripts/inspect_runpod_sequence_result.py "\$latest_result_dir"

## 6. Current speed sprint test: sweep + automatic inspection
ALLOW_RUNPOD_SUFFIX_SPEED_TEST=1 CUDA_ARCH=$CUDA_ARCH_VALUE BENCHMARK_SECONDS=3 \\
  scripts/runpod_gpu_pod_suffix_speed_test.sh

## 7. Fixed GPU Pod autotune: recommended for high-end available cards first
# This detects the GPU with nvidia-smi, chooses the native CUDA arch, uses a
# single-architecture build, and sweeps grid/STEP_SIZE values suitable for that
# GPU class. Prefer RTX PRO 6000 / Blackwell / H100 / H200 / A100 when
# consumer 3090 / 4090 / 5090 inventory is unstable.
ALLOW_RUNPOD_SUFFIX_AUTOTUNE=1 BENCHMARK_SECONDS=3 \\
  scripts/runpod_gpu_pod_suffix_autotune.sh

## 8. Full fixed Pod automation: create Pod, run autotune, fetch result, delete Pod
# Requires RUNPOD_API_KEY in the environment. It refuses to run unless the
# explicit spend gate is set.
scripts/runpod_fixed_pod_autotune_e2e.py --dry-run

ALLOW_RUNPOD_FIXED_POD_AUTOTUNE=1 \\
  scripts/runpod_fixed_pod_autotune_e2e.py

## 9. Optional profiler sweep, only after a short speed sweep is clean
ALLOW_RUNPOD_SUFFIX_SPEED_SWEEP=1 CUDA_ARCH=$CUDA_ARCH_VALUE BENCHMARK_SECONDS=3 \\
RUN_NSYS=1 PROFILE_STEP_SIZE=4096 PROFILE_GRID=64,128 PROFILE_SECONDS=5 \\
  scripts/runpod_gpu_pod_suffix_speed_sweep.sh

## 10. Decision
# If decision = optimize_cuda_before_serverless:
#   stop Serverless work and continue CUDA optimization.
#
# If decision = speed_gate_passed_continue_profiling:
#   proceed to controlled find smoke, then Serverless cold/warm end-to-end tests.
EOF
