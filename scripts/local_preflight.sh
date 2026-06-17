#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== python syntax"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile app.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile flash/runpod_flash_cuda_probe.py
test -x scripts/public_repo_audit.py
test -x scripts/prepare_github_push.sh
test -x scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
test -x scripts/runpod_gpu_pod_sequence.sh
test -x scripts/inspect_runpod_sequence_result.py
test -x scripts/inspect_vanitysearch_benchmark.py
bash -n scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
bash -n scripts/runpod_gpu_pod_sequence.sh
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/inspect_runpod_sequence_result.py

echo "== json"
python3 - <<'PY'
import json
from pathlib import Path

for p in [
    "RUNPOD_VALIDATE_PAYLOAD.json",
    "RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json",
    "RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_FIND_SAMPLE_PAYLOAD.json",
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
    "suffix": "86666",
    "duration_seconds": 1,
    "max_attempts": 1,
})
assert result["allowed"] is False
find_result = app.handle_find({
    "suffix": "CDEFG",
    "age_recipient": "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
    "duration_seconds": 1,
    "max_attempts": 1,
})
assert find_result["allowed"] is False
rule = app.normalize_match_rule({
    "suffix": "86666",
})
assert rule["target_address"].startswith("T")
assert rule["target_address"].endswith("86666")
assert rule["prefix_len"] == 0
assert rule["suffix_len"] == 5
assert rule["search_space"] == 58 ** 5
print("wrapper_gate_ok")
PY
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 tests/verify_find_response_contract.py

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
python3 scripts/public_repo_audit.py >/tmp/tron_gpu_public_repo_audit.json
python3 scripts/validate_goal_rule.py >/tmp/tron_gpu_goal_rule.json
python3 scripts/capacity_math.py --addresses-per-second 1000000000 --seconds 10 >/tmp/tron_gpu_capacity_check.json
python3 scripts/inspect_runpod_result.py examples/runpod_validate_success_sample.json --mode validate_vectors >/tmp/runpod_validate_inspect.json
python3 scripts/inspect_runpod_result.py examples/runpod_benchmark_success_sample.json --mode benchmark >/tmp/runpod_benchmark_inspect.json
python3 scripts/inspect_vanitysearch_benchmark.py examples/vanitysearch_bounded_benchmark_sample.txt >/tmp/vanitysearch_benchmark_inspect.json
sequence_dir="/tmp/tron_gpu_sequence_inspect_sample_$$"
mkdir -p "$sequence_dir"
cleanup_sequence_dir() {
    rm -f \
        "$sequence_dir/vector_gate.stdout.txt" \
        "$sequence_dir/smoke.stdout.txt" \
        "$sequence_dir/benchmark_3s.stdout.txt" \
        "$sequence_dir/benchmark_3s.inspect.json"
    rmdir "$sequence_dir" 2>/dev/null || true
}
trap cleanup_sequence_dir EXIT
printf '%s\n' \
    "tron_gpu_address_layer_passed" \
    "tron_gpu_address_layer_script_passed" \
    "tron_gpu_vector_fields_verified" \
    >"$sequence_dir/vector_gate.stdout.txt"
printf '%s\n' "tron_gpu_pattern_smoke_passed" >"$sequence_dir/smoke.stdout.txt"
printf '%s\n' "tron_gpu_pattern_benchmark_passed" >"$sequence_dir/benchmark_3s.stdout.txt"
printf '%s\n' '{"passed": true, "failures": [], "summary": {"candidate_attempts_per_second_estimate": 800000000, "expected_mean_seconds": 0.82, "p90_seconds": 1.89, "single_worker_meets_goal": true, "required_workers": {"mean_5s": 1, "p90_8s": 1}}}' >"$sequence_dir/benchmark_3s.inspect.json"
python3 scripts/inspect_runpod_sequence_result.py "$sequence_dir" >/tmp/runpod_sequence_inspect.json

echo "== vanitysearch patch gate"
python3 - <<'PY'
from hashlib import sha256
from pathlib import Path

patch = Path("patches/vanitysearch_tron_gpu_suffix_only_20260618.patch")
expected = "eed696759855c331cbac7c68231b33b627511f2df0cb636df4e59befa5ee29a7"
actual = sha256(patch.read_bytes()).hexdigest()
assert actual == expected, actual
print("vanitysearch_patch_sha_ok")
PY
set +e
scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh >/tmp/runpod_vanitysearch_gate_stdout.txt 2>/tmp/runpod_vanitysearch_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected RunPod VanitySearch GPU check script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi

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
    --prefix-len 0 \
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

echo "== non-cuda find gate"
set +e
/tmp/compile_tron_gpu_core_host_stub \
    --find \
    --kernel-mode incremental \
    --target-address TX8888888888888888888888888886666 \
    --prefix-len 0 \
    --suffix-len 5 \
    --duration-seconds 1 \
    --max-attempts 1 \
    --start-counter 0 \
    --shard-id 0 \
    --shard-count 1
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected host-stub find rejection rc=2, got rc=$rc" >&2
    exit 1
fi

echo "local_preflight_passed"
