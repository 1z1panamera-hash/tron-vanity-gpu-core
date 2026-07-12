#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${1:-}"

if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR/GPU" ]; then
  echo "usage: $0 /path/to/exact-round51/VanitySearch" >&2
  exit 2
fi

while read -r file expected; do
  actual="$(shasum -a 256 "$SOURCE_DIR/$file" | awk '{print $1}')"
  if [ "$actual" != "$expected" ]; then
    echo "refusing non-Round51 source: $file" >&2
    echo "expected=$expected" >&2
    echo "actual=$actual" >&2
    exit 3
  fi
done <<'HASHES'
GPU/GPUTronTypes.h 73946fab151979273044cc7b11ace66c5dfd27f7aafb10235926e53d73425128
GPU/GPUTron.h 81a1806f2ba946208176bace23fec704edff07e67eade533f4811d0a611f9f42
GPU/GPUCompute.h 60a2bffd2d110730d62bb551fdaf003d3c8699c5e9518ceb3716a9a851eaf78a
GPU/GPUEngine.h 8a1c6ce879f7bf2f7748f9e3a48fad65c26192a0044eb979c2bb89739763ae0b
GPU/GPUEngine.cu ece350b27465f330ee891bc2e90f9f946f9f8e94a3ec33c0e6a24781d39aa1dd
Vanity.cpp 3423dddb11509a149382db8d2a8183a09185041dd251fc665b4cdb3d96c75768
HASHES

patch --dry-run -p1 -d "$SOURCE_DIR" \
  < "$ROOT/patches/round52_v2_generic_targets.patch"
patch -p1 -d "$SOURCE_DIR" \
  < "$ROOT/patches/round52_v2_generic_targets.patch"

echo "Round52 V2 generic target patch applied"
