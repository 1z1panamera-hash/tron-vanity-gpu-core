#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROUND51_SOURCE_DIR:-/private/tmp/round55_round51_base/VanitySearch}"
CHECK_DIR="${CHECK_DIR:-/private/tmp/vanity_api_v2_round52_patch_check}"

if [ ! -d "$SOURCE_DIR/GPU" ]; then
  echo "exact Round51 source is unavailable; set ROUND51_SOURCE_DIR" >&2
  exit 2
fi

rm -rf "$CHECK_DIR"
mkdir -p "$CHECK_DIR"
cp -R "$SOURCE_DIR/." "$CHECK_DIR/"
"$ROOT/scripts/apply_round52_patch.sh" "$CHECK_DIR"

rg -q "SetTronPatternsV2" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -q "std::vector<std::string> &patterns" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -q "HashTronPipelineCandidateV2" "$CHECK_DIR/GPU/GPUCompute.h"
rg -q "tronGroupsPerLaunch" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -q "targetId = \(metadata >> 2\)" "$CHECK_DIR/GPU/GPUEngine.cu"
rg -Fq "g.SetTronPatternsV2(inputPrefixes)" "$CHECK_DIR/Vanity.cpp"
rg -Fq "patternFound[it.targetId]" "$CHECK_DIR/Vanity.cpp"

echo "Round52 patch apply and static checks passed"
