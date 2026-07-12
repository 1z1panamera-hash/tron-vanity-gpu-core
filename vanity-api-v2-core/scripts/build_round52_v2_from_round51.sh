#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${1:-}"
OUTPUT_DIR="${2:-}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CXXCUDA="${CXXCUDA:-$(command -v g++)}"

if [ "${ALLOW_V2_CUDA_BUILD:-0}" != "1" ]; then
  echo "refusing build without ALLOW_V2_CUDA_BUILD=1" >&2
  exit 2
fi
if [ -z "$SOURCE_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
  echo "usage: $0 /path/to/exact-round51/VanitySearch /path/to/output" >&2
  exit 2
fi
if [ ! -x "$CUDA_HOME/bin/nvcc" ]; then
  echo "nvcc not found under CUDA_HOME=$CUDA_HOME" >&2
  exit 3
fi

mkdir -p "$OUTPUT_DIR"
"$ROOT/scripts/apply_round52_patch.sh" "$SOURCE_DIR"
"$ROOT/scripts/apply_round53_worker_state_patch.sh" "$SOURCE_DIR"

perl -0pi -e \
  's/-gencode=arch=compute_\$\(ccap\),code=sm_\$\(ccap\) -gencode=arch=compute_\$\(ccap\),code=compute_\$\(ccap\)/\$\(NVCC_GENCODE_FLAGS\)/g' \
  "$SOURCE_DIR/Makefile"
perl -0pi -e 's/-maxrregcount=0/-maxrregcount=172/g' "$SOURCE_DIR/Makefile"

DEFINES="-DSTEP_SIZE=16384"
DEFINES="$DEFINES -DTRON_ENABLE_ENDOMORPHISM"
DEFINES="$DEFINES -DTRON_ENABLE_KECCAK_FIXED64_WORDS"
DEFINES="$DEFINES -DTRON_ENABLE_BASE58_LINEAR_RESIDUE"
DEFINES="$DEFINES -DTRON_ENABLE_KECCAK_FIXED64_Y_LANES"
DEFINES="$DEFINES -DTRON_ENABLE_POINT_HASH_PIPELINE"
DEFINES="$DEFINES -DTRON_ENABLE_POINT_HASH_DOUBLE_BUFFER"
GENCODE="-gencode=arch=compute_120,code=sm_120 -gencode=arch=compute_120,code=compute_120"

make -C "$SOURCE_DIR" clean >/dev/null 2>&1 || true
make -C "$SOURCE_DIR" \
  gpu=1 \
  CCAP=120 \
  CUDA="$CUDA_HOME" \
  CXXCUDA="$CXXCUDA" \
  STEP_SIZE=16384 \
  STEP_SIZE_FLAG="$DEFINES" \
  NVCC_GENCODE_FLAGS="$GENCODE" \
  all 2>&1 | tee "$OUTPUT_DIR/build.stdout.txt"

cp "$SOURCE_DIR/VanitySearch" "$OUTPUT_DIR/vanitysearch_v2_round52_step16384"
chmod 0755 "$OUTPUT_DIR/vanitysearch_v2_round52_step16384"

g++ -DWITHGPU $DEFINES -m64 -mssse3 -O2 \
  -I"$SOURCE_DIR" -I"$CUDA_HOME/include" \
  -c "$ROOT/tools/gpu_pattern_matrix.cpp" \
  -o "$SOURCE_DIR/obj/gpu_pattern_matrix.o"
g++ \
  "$SOURCE_DIR/obj/gpu_pattern_matrix.o" \
  "$SOURCE_DIR/obj/Base58.o" \
  "$SOURCE_DIR/obj/IntGroup.o" \
  "$SOURCE_DIR/obj/Random.o" \
  "$SOURCE_DIR/obj/Timer.o" \
  "$SOURCE_DIR/obj/Int.o" \
  "$SOURCE_DIR/obj/IntMod.o" \
  "$SOURCE_DIR/obj/Point.o" \
  "$SOURCE_DIR/obj/SECP256K1.o" \
  "$SOURCE_DIR/obj/GPU/GPUGenerate.o" \
  "$SOURCE_DIR/obj/GPU/GPUEngine.o" \
  "$SOURCE_DIR/obj/hash/ripemd160.o" \
  "$SOURCE_DIR/obj/hash/sha256.o" \
  "$SOURCE_DIR/obj/hash/sha512.o" \
  "$SOURCE_DIR/obj/hash/keccak256.o" \
  "$SOURCE_DIR/obj/hash/ripemd160_sse.o" \
  "$SOURCE_DIR/obj/hash/sha256_sse.o" \
  "$SOURCE_DIR/obj/Bech32.o" \
  "$SOURCE_DIR/obj/Wildcard.o" \
  -lpthread -L"$CUDA_HOME/lib64" -lcudart \
  -o "$OUTPUT_DIR/gpu_pattern_matrix"
chmod 0755 "$OUTPUT_DIR/gpu_pattern_matrix"

g++ -DWITHGPU $DEFINES -m64 -mssse3 -O2 \
  -I"$SOURCE_DIR" -I"$CUDA_HOME/include" \
  -c "$ROOT/tools/gpu_multi_target_benchmark.cpp" \
  -o "$SOURCE_DIR/obj/gpu_multi_target_benchmark.o"
g++ \
  "$SOURCE_DIR/obj/gpu_multi_target_benchmark.o" \
  "$SOURCE_DIR/obj/Base58.o" \
  "$SOURCE_DIR/obj/IntGroup.o" \
  "$SOURCE_DIR/obj/Random.o" \
  "$SOURCE_DIR/obj/Timer.o" \
  "$SOURCE_DIR/obj/Int.o" \
  "$SOURCE_DIR/obj/IntMod.o" \
  "$SOURCE_DIR/obj/Point.o" \
  "$SOURCE_DIR/obj/SECP256K1.o" \
  "$SOURCE_DIR/obj/GPU/GPUGenerate.o" \
  "$SOURCE_DIR/obj/GPU/GPUEngine.o" \
  "$SOURCE_DIR/obj/hash/ripemd160.o" \
  "$SOURCE_DIR/obj/hash/sha256.o" \
  "$SOURCE_DIR/obj/hash/sha512.o" \
  "$SOURCE_DIR/obj/hash/keccak256.o" \
  "$SOURCE_DIR/obj/hash/ripemd160_sse.o" \
  "$SOURCE_DIR/obj/hash/sha256_sse.o" \
  "$SOURCE_DIR/obj/Bech32.o" \
  "$SOURCE_DIR/obj/Wildcard.o" \
  -lpthread -L"$CUDA_HOME/lib64" -lcudart \
  -o "$OUTPUT_DIR/gpu_multi_target_benchmark"
chmod 0755 "$OUTPUT_DIR/gpu_multi_target_benchmark"

g++ -DWITHGPU $DEFINES -m64 -mssse3 -O2 \
  -I"$SOURCE_DIR" -I"$CUDA_HOME/include" \
  -c "$ROOT/tools/gpu_scheduler_benchmark.cpp" \
  -o "$SOURCE_DIR/obj/gpu_scheduler_benchmark.o"
g++ \
  "$SOURCE_DIR/obj/gpu_scheduler_benchmark.o" \
  "$SOURCE_DIR/obj/Base58.o" \
  "$SOURCE_DIR/obj/IntGroup.o" \
  "$SOURCE_DIR/obj/Random.o" \
  "$SOURCE_DIR/obj/Timer.o" \
  "$SOURCE_DIR/obj/Int.o" \
  "$SOURCE_DIR/obj/IntMod.o" \
  "$SOURCE_DIR/obj/Point.o" \
  "$SOURCE_DIR/obj/SECP256K1.o" \
  "$SOURCE_DIR/obj/GPU/GPUGenerate.o" \
  "$SOURCE_DIR/obj/GPU/GPUEngine.o" \
  "$SOURCE_DIR/obj/hash/ripemd160.o" \
  "$SOURCE_DIR/obj/hash/sha256.o" \
  "$SOURCE_DIR/obj/hash/sha512.o" \
  "$SOURCE_DIR/obj/hash/keccak256.o" \
  "$SOURCE_DIR/obj/hash/ripemd160_sse.o" \
  "$SOURCE_DIR/obj/hash/sha256_sse.o" \
  "$SOURCE_DIR/obj/Bech32.o" \
  "$SOURCE_DIR/obj/Wildcard.o" \
  -lpthread -L"$CUDA_HOME/lib64" -lcudart \
  -o "$OUTPUT_DIR/gpu_scheduler_benchmark"
chmod 0755 "$OUTPUT_DIR/gpu_scheduler_benchmark"

g++ -DWITHGPU $DEFINES -std=c++17 -m64 -mssse3 -O2 -Wall -Wextra -Werror \
  -Wno-unused-variable \
  -I"$SOURCE_DIR" -I"$ROOT/include" -I"$CUDA_HOME/include" \
  -c "$ROOT/tools/vanity18035_core_daemon.cpp" \
  -o "$SOURCE_DIR/obj/vanity18035_core_daemon.o"
g++ -std=c++17 -m64 -O2 -Wall -Wextra -Werror \
  -I"$ROOT/include" \
  -c "$ROOT/src/worker_protocol.cpp" \
  -o "$SOURCE_DIR/obj/worker_protocol.o"
g++ -std=c++17 -m64 -O2 -Wall -Wextra -Werror \
  -I"$ROOT/include" \
  -c "$ROOT/src/core_security.cpp" \
  -o "$SOURCE_DIR/obj/core_security.o"
g++ -std=c++17 -m64 -O2 -Wall -Wextra -Werror \
  -I"$ROOT/include" \
  -c "$ROOT/src/tron_pattern.cpp" \
  -o "$SOURCE_DIR/obj/tron_pattern.o"
g++ -std=c++17 -m64 -O2 -Wall -Wextra -Werror \
  -I"$ROOT/include" \
  -c "$ROOT/src/worker_outbox.cpp" \
  -o "$SOURCE_DIR/obj/worker_outbox.o"
g++ \
  "$SOURCE_DIR/obj/vanity18035_core_daemon.o" \
  "$SOURCE_DIR/obj/worker_protocol.o" \
  "$SOURCE_DIR/obj/core_security.o" \
  "$SOURCE_DIR/obj/tron_pattern.o" \
  "$SOURCE_DIR/obj/worker_outbox.o" \
  "$SOURCE_DIR/obj/Base58.o" \
  "$SOURCE_DIR/obj/IntGroup.o" \
  "$SOURCE_DIR/obj/Random.o" \
  "$SOURCE_DIR/obj/Timer.o" \
  "$SOURCE_DIR/obj/Int.o" \
  "$SOURCE_DIR/obj/IntMod.o" \
  "$SOURCE_DIR/obj/Point.o" \
  "$SOURCE_DIR/obj/SECP256K1.o" \
  "$SOURCE_DIR/obj/GPU/GPUGenerate.o" \
  "$SOURCE_DIR/obj/GPU/GPUEngine.o" \
  "$SOURCE_DIR/obj/hash/ripemd160.o" \
  "$SOURCE_DIR/obj/hash/sha256.o" \
  "$SOURCE_DIR/obj/hash/sha512.o" \
  "$SOURCE_DIR/obj/hash/keccak256.o" \
  "$SOURCE_DIR/obj/hash/ripemd160_sse.o" \
  "$SOURCE_DIR/obj/hash/sha256_sse.o" \
  "$SOURCE_DIR/obj/Bech32.o" \
  "$SOURCE_DIR/obj/Wildcard.o" \
  -lpthread -lsqlite3 -L"$CUDA_HOME/lib64" -lcudart \
  -o "$OUTPUT_DIR/vanity18035_core_daemon"
chmod 0755 "$OUTPUT_DIR/vanity18035_core_daemon"

echo "Round52 V2 CUDA build completed"
