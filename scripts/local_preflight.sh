#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== python syntax"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile app.py

echo "== json"
python3 - <<'PY'
import json
from pathlib import Path

for p in [
    "RUNPOD_VALIDATE_PAYLOAD.json",
    "RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json",
    "RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json",
    "src/GPU_CORE_CONTRACT.json",
    "tests/phase0_test_vectors.json",
]:
    json.loads(Path(p).read_text())
    print("json_ok", p)
PY

echo "== wrapper gate"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 - <<'PY'
import os
import app

assert app.cuda_arch_candidates()[:3] == ["native", "sm_120", "sm_80"]
os.environ["CUDA_ARCH"] = "sm_80"
assert app.cuda_arch_candidates()[0] == "sm_80"
os.environ.pop("CUDA_ARCH", None)
result = app.handle_benchmark({
    "target_address": "TX8888888888888888888888888886666",
    "prefix_len": 2,
    "suffix_len": 5,
    "duration_seconds": 1,
    "max_attempts": 1,
})
assert result["allowed"] is False
print("wrapper_gate_ok")
PY

echo "== docker context sanity"
cmp -s Dockerfile Dockerfile.cuda-validate
for p in requirements.txt app.py src tests/phase0_test_vectors.json; do
    test -e "$p"
    if git check-ignore "$p" >/dev/null 2>&1; then
        echo "docker_source_ignored $p" >&2
        exit 1
    fi
    echo "source_ok $p"
done

echo "== sensitive filename scan"
if find . \
    \( -path "./.git" -o -path "./.pycache_tmp" -o -path "./__pycache__" -o -path "./build" \) -prune -o \
    \( -name ".env" -o -name ".env.*" -o -name "*.pem" -o -name "*.key" -o -name "*secret*" -o -name "*token*" \) \
    -print | grep -q .; then
    echo "sensitive-looking filename found" >&2
    find . \
        \( -path "./.git" -o -path "./.pycache_tmp" -o -path "./__pycache__" -o -path "./build" \) -prune -o \
        \( -name ".env" -o -name ".env.*" -o -name "*.pem" -o -name "*.key" -o -name "*secret*" -o -name "*token*" \) \
        -print >&2
    exit 1
fi

echo "== phase0 vectors"
python3 tests/verify_phase0_vectors.py

echo "== core algorithms"
c++ -std=c++17 -O2 tests/verify_core_algorithms.cpp -o /tmp/verify_core_algorithms
/tmp/verify_core_algorithms

echo "== device-compatible algorithms"
c++ -std=c++17 -O2 tests/verify_device_compatible_algorithms.cpp -o /tmp/verify_device_compatible_algorithms
/tmp/verify_device_compatible_algorithms

echo "== secp256k1 full chain"
c++ -std=c++17 -O2 tests/verify_secp256k1_full_chain.cpp -o /tmp/verify_secp256k1_full_chain
/tmp/verify_secp256k1_full_chain

echo "== secp256k1 device-compatible"
c++ -std=c++17 -O2 tests/verify_secp256k1_device_compatible.cpp -o /tmp/verify_secp256k1_device_compatible
/tmp/verify_secp256k1_device_compatible

echo "== batch inversion"
c++ -std=c++17 -O2 tests/verify_batch_inversion.cpp -o /tmp/verify_batch_inversion
/tmp/verify_batch_inversion

echo "== batch point add"
c++ -std=c++17 -O2 tests/verify_batch_point_add.cpp -o /tmp/verify_batch_point_add
/tmp/verify_batch_point_add

echo "== result inspectors"
python3 scripts/capacity_math.py --addresses-per-second 1000000000 --seconds 10 >/tmp/tron_gpu_capacity_check.json
python3 scripts/inspect_runpod_result.py examples/runpod_validate_success_sample.json --mode validate_vectors >/tmp/runpod_validate_inspect.json
python3 scripts/inspect_runpod_result.py examples/runpod_benchmark_success_sample.json --mode benchmark >/tmp/runpod_benchmark_inspect.json

echo "== incremental walking"
c++ -std=c++17 -O2 tests/verify_incremental_walking.cpp -o /tmp/verify_incremental_walking
/tmp/verify_incremental_walking

echo "== shard schedule"
c++ -std=c++17 -O2 tests/verify_shard_schedule.cpp -o /tmp/verify_shard_schedule
/tmp/verify_shard_schedule

echo "== non-cuda benchmark gate"
c++ -std=c++17 -O2 -x c++ tests/compile_tron_gpu_core_host_stub.cpp -o /tmp/compile_tron_gpu_core_host_stub
set +e
/tmp/compile_tron_gpu_core_host_stub \
    --benchmark \
    --kernel-mode incremental \
    --target-address TX8888888888888888888888888886666 \
    --prefix-len 2 \
    --suffix-len 5 \
    --duration-seconds 5 \
    --max-attempts 1 \
    --start-counter 0 \
    --shard-id 0 \
    --shard-count 1
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected host-stub benchmark rejection rc=2, got rc=$rc" >&2
    exit 1
fi

echo "local_preflight_passed"
