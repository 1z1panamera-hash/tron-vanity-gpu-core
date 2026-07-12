#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${1:-}"

if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/GPU/GPUEngine.cu" ]; then
  echo "usage: $0 /path/to/round52/VanitySearch" >&2
  exit 2
fi

if grep -q "ExportKeyState" "$SOURCE_DIR/GPU/GPUEngine.cu"; then
  echo "Round53 worker state patch already applied"
  exit 0
fi

patch -d "$SOURCE_DIR" -p1 < "$ROOT/patches/round53_worker_state_api.patch"
grep -q "ExportKeyState" "$SOURCE_DIR/GPU/GPUEngine.cu"
grep -q "ImportKeyState" "$SOURCE_DIR/GPU/GPUEngine.h"
echo "Round53 worker state patch applied"
