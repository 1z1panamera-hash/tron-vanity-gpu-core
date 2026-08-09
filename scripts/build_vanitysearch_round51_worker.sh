#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VANITYSEARCH_COMMIT="${VANITYSEARCH_COMMIT:-c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b}"
VANITYSEARCH_SOURCE_DIR="${VANITYSEARCH_SOURCE_DIR:-}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-round51-worker-build}"
INSTALL_PATH="${INSTALL_PATH:-$ROOT/build/vanitysearch_tron_worker_round51_sm120}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CXXCUDA="${CXXCUDA:-/usr/bin/g++}"
CUDA_ARCH="${CUDA_ARCH:-sm_120}"
STEP_SIZE="${STEP_SIZE:-16384}"
NVCC_MAXRREGCOUNT="${NVCC_MAXRREGCOUNT:-172}"

PATCH_NAMES=(
  vanitysearch_tron_gpu_suffix_only_20260618.patch
  vanitysearch_tron_gpu_5090_round2_tron_endo.patch
  vanitysearch_tron_gpu_5090_round10_keccak_sparse_init.patch
  vanitysearch_tron_gpu_5090_round18_keccak_fixed64_words.patch
  vanitysearch_tron_gpu_5090_round19_base58_linear_residue.patch
  vanitysearch_tron_gpu_5090_round20_fixed64_y_lanes.patch
  vanitysearch_tron_gpu_5090_round32_prefix_gate_fixed64_y_lanes.patch
  vanitysearch_tron_gpu_5090_round33_prefix_fixed64_prune_debug_flags.patch
  vanitysearch_tron_gpu_5090_round50_point_hash_pipeline.patch
  vanitysearch_tron_gpu_5090_round51_pipeline_double_buffer.patch
)
PATCH_SHAS=(
  571a864d3d76adc536251e7199a4c572200440adcb0770634b41b295aa7d993a
  e0f34cf9e7ef2619e671c17ff24ebd5034705197b5496005dfe74e587d99486c
  c8f325c3b4fd70ac37756a643807214b1df3df822a71a7887966774f8f59ccb8
  17c7b18e26876b5b29731033eda41a9f6d0ca22767434c07023a74e4483d7f49
  3a447472dcb54a103c69a7ef08b48a2a3f8494df50110b6fdf72d69b8cac4b0f
  ae17ae929cefc32a0fb367924537e2b6768b3273b331ad502705940d4538fb30
  0d835f2e763a6d50743c26b997992ed82be04da7a563abea842ccf85ed78181f
  0de6676bb939c2bd4db6cd253cab5b72ca2aa60ba116c05cad04b815a032e41e
  c89c28b1c5ebb2756e1f4785dd04bd180fbd6526636c7612b90c10b9b16474b0
  242b90ff98b701123ceea91970c1e7fa476ea0a59ac8a93d9ef299fe6432bd0a
)

if [ "${ALLOW_BUILD_VANITYSEARCH_ROUND51_WORKER:-0}" != "1" ]; then
  echo "refusing_to_build_without_ALLOW_BUILD_VANITYSEARCH_ROUND51_WORKER=1" >&2
  exit 2
fi
if [ "$CUDA_ARCH" != "sm_120" ]; then
  echo "Round51 worker is approved only for CUDA_ARCH=sm_120" >&2
  exit 2
fi
if [ "$STEP_SIZE" != "16384" ] || [ "$NVCC_MAXRREGCOUNT" != "172" ]; then
  echo "Round51 worker requires STEP_SIZE=16384 and NVCC_MAXRREGCOUNT=172" >&2
  exit 2
fi
if [ -z "$VANITYSEARCH_SOURCE_DIR" ] || [ ! -f "$VANITYSEARCH_SOURCE_DIR/Makefile" ]; then
  echo "VANITYSEARCH_SOURCE_DIR must point to the pinned VanitySearch checkout" >&2
  exit 2
fi

for index in "${!PATCH_NAMES[@]}"; do
  patch_path="$ROOT/patches/${PATCH_NAMES[$index]}"
  if [ ! -f "$patch_path" ]; then
    echo "missing patch: ${PATCH_NAMES[$index]}" >&2
    exit 1
  fi
  actual_sha="$(sha256sum "$patch_path" | awk '{print $1}')"
  if [ "$actual_sha" != "${PATCH_SHAS[$index]}" ]; then
    echo "patch sha256 mismatch: ${PATCH_NAMES[$index]}" >&2
    exit 1
  fi
done

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR/VanitySearch" "$(dirname "$INSTALL_PATH")"
cp -a "$VANITYSEARCH_SOURCE_DIR/." "$WORKDIR/VanitySearch/"
if git -C "$WORKDIR/VanitySearch" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  source_commit="$(git -C "$WORKDIR/VanitySearch" rev-parse HEAD)"
  if [ "$source_commit" != "$VANITYSEARCH_COMMIT" ]; then
    echo "VanitySearch source commit mismatch" >&2
    exit 1
  fi
fi
rm -rf "$WORKDIR/VanitySearch/.git"
cd "$WORKDIR/VanitySearch"

for header in Timer.h hash/sha256.h hash/sha512.h; do
  if ! grep -q '#include <cstdint>' "$header"; then
    sed -i.bak '/#include <string>/a\
#include <cstdint>
' "$header"
    rm -f "$header.bak"
  fi
done

for patch_name in "${PATCH_NAMES[@]}"; do
  if [ "$patch_name" = "vanitysearch_tron_gpu_5090_round20_fixed64_y_lanes.patch" ]; then
    git apply --recount --unidiff-zero "$ROOT/patches/$patch_name"
  else
    git apply --recount "$ROOT/patches/$patch_name"
  fi
done

if [ "${PATCH_ONLY:-0}" = "1" ]; then
  grep -q 'TRON_ENABLE_POINT_HASH_DOUBLE_BUFFER' GPU/GPUEngine.cu
  grep -q 'HashTronPipelineCandidate' GPU/GPUCompute.h
  echo "vanitysearch_round51_sm120_patch_stack_applied"
  exit 0
fi

sed -i.bak \
  's|-gencode=arch=compute_$(ccap),code=sm_$(ccap) -gencode=arch=compute_$(ccap),code=compute_$(ccap)|$(NVCC_GENCODE_FLAGS)|g' \
  Makefile
rm -f Makefile.bak
sed -i.bak "s|-maxrregcount=0|-maxrregcount=${NVCC_MAXRREGCOUNT}|g" Makefile
rm -f Makefile.bak

DEFINES="-DSTEP_SIZE=16384"
DEFINES="$DEFINES -DTRON_ENABLE_ENDOMORPHISM"
DEFINES="$DEFINES -DTRON_ENABLE_KECCAK_FIXED64_WORDS"
DEFINES="$DEFINES -DTRON_ENABLE_BASE58_LINEAR_RESIDUE"
DEFINES="$DEFINES -DTRON_ENABLE_KECCAK_FIXED64_Y_LANES"
DEFINES="$DEFINES -DTRON_ENABLE_POINT_HASH_PIPELINE"
DEFINES="$DEFINES -DTRON_ENABLE_POINT_HASH_DOUBLE_BUFFER"
GENCODE="-gencode=arch=compute_120,code=sm_120 -gencode=arch=compute_120,code=compute_120"

make clean >/dev/null 2>&1 || true
make gpu=1 \
  CCAP=120 \
  CUDA="$CUDA_HOME" \
  CXXCUDA="$CXXCUDA" \
  STEP_SIZE=16384 \
  STEP_SIZE_FLAG="$DEFINES" \
  NVCC_GENCODE_FLAGS="$GENCODE" \
  all

cp ./VanitySearch "$INSTALL_PATH"
chmod 0755 "$INSTALL_PATH"
echo "vanitysearch_round51_sm120_worker_built"
