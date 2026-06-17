#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_address_layer_20260618.patch"

if [ "${ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1" >&2
  echo "This script is intended for a short-lived CUDA RunPod Pod only." >&2
  exit 2
fi

if [ ! -f "$PATCH_PATH" ]; then
  echo "missing patch: $PATCH_PATH" >&2
  exit 1
fi

EXPECTED_SHA="a988726c561760768ba20d3b7354b497a27fa59e437c08046f73d1136e0825fc"
ACTUAL_SHA="$(sha256sum "$PATCH_PATH" | awk '{print $1}')"
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
  echo "patch sha256 mismatch" >&2
  echo "expected=$EXPECTED_SHA" >&2
  echo "actual=$ACTUAL_SHA" >&2
  exit 1
fi

VANITYSEARCH_REPO="${VANITYSEARCH_REPO:-https://github.com/JeanLucPons/VanitySearch.git}"
VANITYSEARCH_COMMIT="${VANITYSEARCH_COMMIT:-c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-tron-gpu-address-layer-$(date +%s)}"
CUDA_ARCH="${CUDA_ARCH:-sm_80}"

if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi
mkdir -p "$WORKDIR"

echo "== clone VanitySearch candidate base"
git clone --quiet "$VANITYSEARCH_REPO" "$WORKDIR/VanitySearch"
cd "$WORKDIR/VanitySearch"
git checkout --quiet "$VANITYSEARCH_COMMIT"

echo "== apply TRON GPU address layer patch"
git apply "$PATCH_PATH"

echo "== run GPU TRON address layer vector check"
CUDA_ARCH="$CUDA_ARCH" scripts/runpod_verify_tron_gpu_address_layer.sh
