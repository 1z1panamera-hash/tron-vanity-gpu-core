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
    "src/GPU_CORE_CONTRACT.json",
    "tests/phase0_test_vectors.json",
]:
    json.loads(Path(p).read_text())
    print("json_ok", p)
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

echo "== result inspectors"
python3 scripts/capacity_math.py --addresses-per-second 1000000000 --seconds 10 >/tmp/tron_gpu_capacity_check.json
python3 - <<'PY'
import json
from pathlib import Path

validate_sample = {
    "mode": "validate_vectors",
    "phase0_vectors": {"passed": True},
    "compile": {"ready": True, "elapsed_seconds": 1.0},
    "gpu_binary": {"returncode": 0},
    "passed": True,
}
benchmark_sample = {
    "mode": "benchmark",
    "benchmark_result": {
        "kernel_mode": "incremental_public_key_walk",
        "gpu_name": "TEST_GPU",
        "attempts": 1024,
        "addresses_per_second": 1024.0,
        "keys_per_second": 1024.0,
        "matched": False,
        "matched_address": "",
    },
}
Path("/tmp/runpod_validate_sample.json").write_text(json.dumps(validate_sample))
Path("/tmp/runpod_benchmark_sample.json").write_text(json.dumps(benchmark_sample))
PY
python3 scripts/inspect_runpod_result.py /tmp/runpod_validate_sample.json --mode validate_vectors >/tmp/runpod_validate_inspect.json
python3 scripts/inspect_runpod_result.py /tmp/runpod_benchmark_sample.json --mode benchmark >/tmp/runpod_benchmark_inspect.json

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
