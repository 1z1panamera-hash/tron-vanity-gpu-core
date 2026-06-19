#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_suffix_only_20260618.patch"
EXPECTED_PATCH_SHA="0dfac1bda53b647ae88c2d5772aa65913224e3fd523f4c54ae31a2d42f366204"

if [ "${ALLOW_BUILD_VANITYSEARCH_TRON_WORKER:-0}" != "1" ]; then
  echo "refusing_to_build_without_ALLOW_BUILD_VANITYSEARCH_TRON_WORKER=1" >&2
  echo "This clones upstream VanitySearch and compiles CUDA. Run only in an approved GPU build image or RunPod build." >&2
  exit 2
fi

if [ ! -f "$PATCH_PATH" ]; then
  echo "missing patch: $PATCH_PATH" >&2
  exit 1
fi

actual_sha="$(sha256sum "$PATCH_PATH" | awk '{print $1}')"
if [ "$actual_sha" != "$EXPECTED_PATCH_SHA" ]; then
  echo "patch sha256 mismatch" >&2
  echo "expected=$EXPECTED_PATCH_SHA" >&2
  echo "actual=$actual_sha" >&2
  exit 1
fi

VANITYSEARCH_REPO="${VANITYSEARCH_REPO:-https://github.com/JeanLucPons/VanitySearch.git}"
VANITYSEARCH_COMMIT="${VANITYSEARCH_COMMIT:-c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-tron-worker-build}"
INSTALL_PATH="${INSTALL_PATH:-$ROOT/build/vanitysearch_tron_worker}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CUDA_ARCH_INPUT="${CUDA_ARCH:-sm_120}"
CCAP="${CUDA_ARCH_INPUT#sm_}"
CUDA_ARCHS_INPUT="${CUDA_ARCHS:-}"
CXXCUDA="${CXXCUDA:-/usr/bin/g++}"
STEP_SIZE="${STEP_SIZE:-4096}"

case "$STEP_SIZE" in
  ''|*[!0-9]*)
    echo "STEP_SIZE must be an integer: $STEP_SIZE" >&2
    exit 1
    ;;
esac
if [ $((STEP_SIZE % 1024)) -ne 0 ]; then
  echo "STEP_SIZE must be a multiple of 1024: $STEP_SIZE" >&2
  exit 1
fi

if [ -e "$WORKDIR" ]; then
  rm -rf "$WORKDIR"
fi
mkdir -p "$WORKDIR" "$(dirname "$INSTALL_PATH")"

echo "== build patched VanitySearch TRON worker"
echo "vanitysearch_repo=$VANITYSEARCH_REPO"
echo "vanitysearch_commit=$VANITYSEARCH_COMMIT"
echo "cuda_arch=$CUDA_ARCH_INPUT"
echo "cuda_archs=${CUDA_ARCHS_INPUT:-single:${CUDA_ARCH_INPUT}}"
echo "ccap=$CCAP"
echo "step_size=$STEP_SIZE"
echo "install_path=$INSTALL_PATH"

git clone --quiet "$VANITYSEARCH_REPO" "$WORKDIR/VanitySearch"
cd "$WORKDIR/VanitySearch"
git checkout --quiet "$VANITYSEARCH_COMMIT"

for header in Timer.h hash/sha256.h hash/sha512.h; do
  if ! grep -q '#include <cstdint>' "$header"; then
    sed -i '/#include <string>/a #include <cstdint>' "$header"
  fi
done

git apply "$PATCH_PATH"

NVCC_GENCODE_FLAGS=""
if [ -n "$CUDA_ARCHS_INPUT" ]; then
  IFS=',' read -r -a cuda_archs <<< "$CUDA_ARCHS_INPUT"
  for arch in "${cuda_archs[@]}"; do
    arch="${arch//[[:space:]]/}"
    if [[ ! "$arch" =~ ^sm_[0-9]+$ ]]; then
      echo "CUDA_ARCHS entries must look like sm_80,sm_86,sm_89,sm_120: $arch" >&2
      exit 1
    fi
    ccap_multi="${arch#sm_}"
    NVCC_GENCODE_FLAGS+=" -gencode=arch=compute_${ccap_multi},code=sm_${ccap_multi}"
  done
  last_index=$((${#cuda_archs[@]} - 1))
  last_arch="${cuda_archs[$last_index]//[[:space:]]/}"
  last_ccap="${last_arch#sm_}"
  NVCC_GENCODE_FLAGS+=" -gencode=arch=compute_${last_ccap},code=compute_${last_ccap}"
  sed -i 's|-gencode=arch=compute_$(ccap),code=sm_$(ccap) -gencode=arch=compute_$(ccap),code=compute_$(ccap)|$(NVCC_GENCODE_FLAGS)|g' Makefile
  echo "nvcc_gencode_flags=$NVCC_GENCODE_FLAGS"
fi

if [ "${RUN_VANITYSEARCH_GPU_VECTOR_CHECK:-0}" = "1" ]; then
  CUDA_ARCH="$CUDA_ARCH_INPUT" scripts/runpod_verify_tron_gpu_address_layer.sh
else
  echo "skipping_gpu_vector_check_during_build"
  echo "Set RUN_VANITYSEARCH_GPU_VECTOR_CHECK=1 only in an approved GPU runtime, not during Serverless image build."
fi

make gpu=1 CCAP="$CCAP" CUDA="$CUDA_HOME" CXXCUDA="$CXXCUDA" STEP_SIZE="$STEP_SIZE" NVCC_GENCODE_FLAGS="$NVCC_GENCODE_FLAGS" all
cp ./VanitySearch "$INSTALL_PATH"
chmod 0755 "$INSTALL_PATH"

echo "vanitysearch_tron_worker_built"
