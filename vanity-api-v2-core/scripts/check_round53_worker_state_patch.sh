#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROUND51_SOURCE_DIR:-/private/tmp/round55_round51_base/VanitySearch}"
CHECK_DIR="${CHECK_DIR:-/private/tmp/vanity_api_v2_round53_patch_check}"

if [ ! -d "$SOURCE_DIR/GPU" ]; then
  echo "exact Round51 source is unavailable; set ROUND51_SOURCE_DIR" >&2
  exit 2
fi

rm -rf "$CHECK_DIR"
mkdir -p "$CHECK_DIR"
cp -R "$SOURCE_DIR/." "$CHECK_DIR/"
"$ROOT/scripts/apply_round52_patch.sh" "$CHECK_DIR"
"$ROOT/scripts/apply_round53_worker_state_patch.sh" "$CHECK_DIR"

rg -q "GetKeyStateWordCount" "$CHECK_DIR/GPU/GPUEngine.h"
rg -q "cudaMemcpyDeviceToHost" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -q "return callKernel\(\);" "$CHECK_DIR/GPU/GPUEngine.cu"
! rg -q "^[[:space:]]*SetPattern\(pattern\);" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -q "this->pattern = std::string\(pattern\)" "$CHECK_DIR/GPU/GPUEngine.cu"

echo "Round53 worker state patch apply and static checks passed"
