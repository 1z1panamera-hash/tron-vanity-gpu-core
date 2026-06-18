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
test -x scripts/runpod_gpu_pod_suffix_speed_sweep.sh
test -x scripts/runpod_gpu_pod_suffix_speed_test.sh
test -x scripts/runpod_gpu_pod_find_debug.sh
test -x scripts/runpod_gpu_pod_suffix_compare_commits.sh
test -x scripts/build_vanitysearch_tron_worker.sh
test -x scripts/runpod_serverless_find_e2e.py
test -x scripts/runpod_serverless_readiness_check.py
test -x scripts/prepare_runpod_smoke_test_materials.py
test -x scripts/generate_test_age_identity.py
test -x scripts/verify_age_encrypted_find_response.py
test -x scripts/inspect_suffix_speed_sweep.py
test -x scripts/inspect_runpod_sequence_result.py
test -x scripts/inspect_serverless_find_e2e.py
test -x scripts/print_runpod_suffix_only_commands.sh
test -x scripts/inspect_vanitysearch_benchmark.py
bash -n scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
bash -n scripts/runpod_gpu_pod_sequence.sh
bash -n scripts/runpod_gpu_pod_suffix_speed_sweep.sh
bash -n scripts/runpod_gpu_pod_suffix_speed_test.sh
bash -n scripts/runpod_gpu_pod_find_debug.sh
bash -n scripts/runpod_gpu_pod_suffix_compare_commits.sh
bash -n scripts/build_vanitysearch_tron_worker.sh
bash -n scripts/print_runpod_suffix_only_commands.sh
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/runpod_serverless_find_e2e.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/runpod_serverless_readiness_check.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/prepare_runpod_smoke_test_materials.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/generate_test_age_identity.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/verify_age_encrypted_find_response.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/inspect_runpod_sequence_result.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/inspect_suffix_speed_sweep.py
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 -m py_compile scripts/inspect_serverless_find_e2e.py

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
rule = app.normalize_match_rule({
    "suffix": "86666",
})
assert rule["target_address"].startswith("T")
assert rule["target_address"].endswith("86666")
assert rule["prefix_len"] == 0
assert rule["suffix_len"] == 5
assert rule["search_space"] == 58 ** 5
speed = app.parse_vanitysearch_speed("[1.23 Mkey/s][GPU 456.78 Mkey/s]")
assert speed["candidate_attempts_per_second_estimate"] == 456_780_000.0
assert app.contains_forbidden_output_marker("TRON_SUPPRESS_SECRET_OUTPUT=1") is False
assert app.contains_forbidden_output_marker("Priv (HEX): 0xabc") is True
assert app.selected_gpu_backend() in {"self", "vanitysearch"}
print("wrapper_gate_ok")
PY

echo "== docker context sanity"
cmp -s Dockerfile Dockerfile.cuda-validate
for p in requirements.txt app.py src patches scripts/build_vanitysearch_tron_worker.sh scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh tests/phase0_test_vectors.json; do
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
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/tron_gpu_core_pycache}" python3 tests/verify_find_response_contract.py >/tmp/tron_gpu_find_response_contract.json
python3 scripts/public_repo_audit.py >/tmp/tron_gpu_public_repo_audit.json
python3 scripts/runpod_serverless_readiness_check.py >/tmp/runpod_serverless_readiness_check.json
python3 scripts/validate_goal_rule.py >/tmp/tron_gpu_goal_rule.json
python3 scripts/generate_test_age_identity.py \
    --identity "/tmp/tron_gpu_generated_age_identity_$$.txt" \
    >/tmp/generated_test_age_identity.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/generated_test_age_identity.json").read_text())
assert data["passed"] is True
assert data["recipient"].startswith("age1")
identity = Path(data["identity_path"])
assert identity.exists()
assert str(identity).startswith("/tmp/")
text = Path("/tmp/generated_test_age_identity.json").read_text()
assert "AGE-SECRET-KEY-" not in text
identity.unlink()
PY
smoke_material_dir="/tmp/tron_gpu_smoke_materials_$$"
fake_age_keygen="$smoke_material_dir/fake_age_keygen"
mkdir -p "$smoke_material_dir"
cat >"$fake_age_keygen" <<'SH'
#!/usr/bin/env bash
if [ "$1" != "-o" ]; then
  exit 2
fi
printf '%s\n' "AGE-SECRET-KEY-TEST-ONLY" >"$2"
printf '%s\n' "Public key: age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
SH
chmod +x "$fake_age_keygen"
python3 scripts/prepare_runpod_smoke_test_materials.py \
    --out-dir "$smoke_material_dir/out" \
    --age-keygen-binary "$fake_age_keygen" \
    >/tmp/runpod_smoke_materials_check.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/runpod_smoke_materials_check.json").read_text())
assert data["passed"] is True
assert data["recipient"].startswith("age1")
payload = json.loads(Path(data["payload_path"]).read_text())
assert payload["input"]["mode"] == "find"
assert payload["input"]["suffix"] == "CDEFG"
assert payload["input"]["age_recipient"] == data["recipient"]
assert "prefix_len" not in payload["input"]
assert "suffix_len" not in payload["input"]
assert "prefix_after_t" not in payload["input"]
identity = Path(data["identity_path"])
assert identity.exists()
assert str(identity).startswith("/tmp/")
PY
python3 scripts/prepare_runpod_smoke_test_materials.py \
    --out-dir "$smoke_material_dir/out_python_keygen" \
    --python-age-keygen \
    >/tmp/runpod_smoke_materials_python_keygen_check.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/runpod_smoke_materials_python_keygen_check.json").read_text())
assert data["passed"] is True
assert data["identity_written"] is True
assert data["recipient"].startswith("age1")
assert Path(data["identity_path"]).exists()
assert "AGE-SECRET-KEY-" not in Path("/tmp/runpod_smoke_materials_python_keygen_check.json").read_text()
PY
python3 scripts/prepare_runpod_smoke_test_materials.py \
    --out-dir "$smoke_material_dir/out_existing_recipient" \
    --age-recipient age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq \
    >/tmp/runpod_smoke_materials_existing_recipient_check.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/runpod_smoke_materials_existing_recipient_check.json").read_text())
assert data["passed"] is True
assert data["identity_written"] is False
assert data["identity_path"] is None
payload = json.loads(Path(data["payload_path"]).read_text())
assert payload["input"]["age_recipient"] == data["recipient"]
PY
rm -rf "$smoke_material_dir"
python3 scripts/capacity_math.py --addresses-per-second 1000000000 --seconds 10 >/tmp/tron_gpu_capacity_check.json
python3 scripts/inspect_runpod_result.py examples/runpod_validate_success_sample.json --mode validate_vectors >/tmp/runpod_validate_inspect.json
python3 scripts/inspect_runpod_result.py examples/runpod_benchmark_success_sample.json --mode benchmark >/tmp/runpod_benchmark_inspect.json
python3 scripts/inspect_runpod_result.py examples/runpod_find_success_sample.json --mode find >/tmp/runpod_find_inspect.json
age_verify_dir="/tmp/tron_gpu_age_verify_$$"
mkdir -p "$age_verify_dir"
cat >"$age_verify_dir/age" <<'SH'
#!/usr/bin/env bash
printf '%064d\n' 1
SH
chmod +x "$age_verify_dir/age"
printf '%s\n' "AGE-SECRET-KEY-TEST-ONLY" >"$age_verify_dir/test_identity.txt"
python3 scripts/verify_age_encrypted_find_response.py \
    examples/runpod_find_success_sample.json \
    --identity "$age_verify_dir/test_identity.txt" \
    --age-binary "$age_verify_dir/age" \
    >/tmp/age_find_response_verify.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/age_find_response_verify.json").read_text())
assert data["passed"] is True, data["failures"]
assert data["age_decrypt_passed"] is True
text = Path("/tmp/age_find_response_verify.json").read_text()
assert "0000000000000000000000000000000000000000000000000000000000000001" not in text
PY
cat >"$age_verify_dir/age_bad" <<'SH'
#!/usr/bin/env bash
printf '%s\n' not-a-hex-secret
SH
chmod +x "$age_verify_dir/age_bad"
set +e
python3 scripts/verify_age_encrypted_find_response.py \
    examples/runpod_find_success_sample.json \
    --identity "$age_verify_dir/test_identity.txt" \
    --age-binary "$age_verify_dir/age_bad" \
    >/tmp/age_find_response_bad_verify.json
rc=$?
set -e
rm -rf "$age_verify_dir"
if [ "$rc" -eq 0 ]; then
    echo "expected bad age decrypt verifier to fail" >&2
    exit 1
fi
python3 scripts/inspect_vanitysearch_benchmark.py examples/vanitysearch_bounded_benchmark_sample.txt >/tmp/vanitysearch_benchmark_inspect.json
bad_find_file="/tmp/tron_gpu_bad_find_response_$$.json"
cat >"$bad_find_file" <<'JSON'
{
  "output": {
    "mode": "find",
    "matched": true,
    "matched_address": "TA11111111111111111111111111CDEFG",
    "encrypted_private_key": "-----BEGIN AGE ENCRYPTED FILE-----\nYWdlLWVuY3J5cHRlZC10ZXN0LWNpcGhlcnRleHQ=\n-----END AGE ENCRYPTED FILE-----",
    "private_key_hex": "0000000000000000000000000000000000000000000000000000000000000001",
    "match_rule": {"prefix_len": 0, "suffix_len": 5, "suffix": "CDEFG", "search_space": 656356768}
  }
}
JSON
set +e
python3 scripts/inspect_runpod_result.py "$bad_find_file" --mode find >/tmp/runpod_bad_find_inspect.json
rc=$?
set -e
rm -f "$bad_find_file"
if [ "$rc" -eq 0 ]; then
    echo "expected bad find response inspection to fail" >&2
    exit 1
fi
serverless_find_dir="/tmp/tron_gpu_serverless_find_e2e_$$"
mkdir -p "$serverless_find_dir"
cleanup_serverless_find_dir() {
    rm -f "$serverless_find_dir"/*.json
    rmdir "$serverless_find_dir" 2>/dev/null || true
}
python3 - "$serverless_find_dir" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
(out / "manifest.json").write_text(json.dumps({
    "mode": "runpod_serverless_find_e2e_manifest",
    "samples": 11,
    "cold_count": 1,
}) + "\n")
base = {
    "status": "COMPLETED",
    "output": {
        "mode": "find",
        "allowed": True,
        "matched": True,
        "gpu_worker_backend": "vanitysearch",
        "matched_address": "TA11111111111111111111111111CDEFG",
        "encrypted_private_key": "-----BEGIN AGE ENCRYPTED FILE-----\nYWdlLWVuY3J5cHRlZC10ZXN0LWNpcGhlcnRleHQ=\n-----END AGE ENCRYPTED FILE-----",
        "match_rule": {
            "target_address": "T888888888888888888888888888CDEFG",
            "prefix_len": 0,
            "suffix_len": 5,
            "suffix": "CDEFG",
            "effective_random_chars": 5,
            "search_space": 656356768,
            "rule": "TRON suffix-only last 5 Base58 characters",
        },
        "elapsed_seconds": 0.7,
        "gpu_grid": "128,128",
    },
}
latencies = [7.2, 1.4, 1.3, 1.2, 1.6, 1.5, 1.7, 1.8, 1.1, 1.4, 1.6]
for index, latency in enumerate(latencies):
    item = dict(base)
    item["id"] = f"sample-{index:02d}"
    item["request_latency_seconds"] = latency
    (out / f"find_{index:02d}.json").write_text(json.dumps(item, indent=2) + "\n")
PY
batch_age_verify_dir="/tmp/tron_gpu_batch_age_verify_$$"
mkdir -p "$batch_age_verify_dir"
cat >"$batch_age_verify_dir/age" <<'SH'
#!/usr/bin/env bash
printf '%064d\n' 1
SH
chmod +x "$batch_age_verify_dir/age"
printf '%s\n' "AGE-SECRET-KEY-TEST-ONLY" >"$batch_age_verify_dir/test_identity.txt"
python3 scripts/inspect_serverless_find_e2e.py \
    "$serverless_find_dir" \
    --cold-count 1 \
    --age-identity "$batch_age_verify_dir/test_identity.txt" \
    --age-binary "$batch_age_verify_dir/age" \
    >/tmp/serverless_find_e2e_inspect.json
rm -rf "$batch_age_verify_dir"
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/serverless_find_e2e_inspect.json").read_text())
assert data["passed"] is True, data["failures"]
assert data["cold_count"] == 1
assert data["warm_count"] == 10
assert data["warm_average_seconds"] <= 5.0
assert data["warm_p90_seconds"] <= 8.0
assert data["age_decrypt_checked_count"] == 11
assert data["age_decrypt_passed_count"] == 11
assert "0000000000000000000000000000000000000000000000000000000000000001" not in Path("/tmp/serverless_find_e2e_inspect.json").read_text()
PY
scripts/runpod_serverless_find_e2e.py \
    --dry-run \
    --endpoint-id test-endpoint \
    --age-recipient age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq \
    --samples 11 \
    --cold-count 1 \
    >/tmp/runpod_serverless_find_e2e_dry_run.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/runpod_serverless_find_e2e_dry_run.json").read_text())
assert data["mode"] == "runpod_serverless_find_e2e_dry_run"
assert data["would_call_runpod"] is False
assert data["payload"]["input"]["mode"] == "find"
assert data["payload"]["input"]["suffix"] == "CDEFG"
assert data["allow_short_smoke"] is False
PY
scripts/runpod_serverless_find_e2e.py \
    --dry-run \
    --allow-short-smoke \
    --endpoint-id test-endpoint \
    --age-recipient age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq \
    --samples 1 \
    --cold-count 0 \
    >/tmp/runpod_serverless_find_smoke_dry_run.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/runpod_serverless_find_smoke_dry_run.json").read_text())
assert data["mode"] == "runpod_serverless_find_e2e_dry_run"
assert data["would_call_runpod"] is False
assert data["samples"] == 1
assert data["cold_count"] == 0
assert data["allow_short_smoke"] is True
PY
speed_sweep_dir="/tmp/tron_gpu_suffix_speed_sweep_inspect_sample_$$"
mkdir -p "$speed_sweep_dir"
cleanup_speed_sweep_dir() {
    rm -f \
        "$speed_sweep_dir/speed_sweep_summary.json" \
        "$speed_sweep_dir/gpu_utilization.csv" \
        "$speed_sweep_dir/build_step_1024.stdout.txt" \
        "$speed_sweep_dir/build_step_4096.stdout.txt"
    rmdir "$speed_sweep_dir" 2>/dev/null || true
}
trap cleanup_speed_sweep_dir EXIT
cat >"$speed_sweep_dir/speed_sweep_summary.json" <<'JSON'
{
  "mode": "suffix_speed_sweep_summary",
  "passed": true,
  "best_step_size": 1024,
  "best_grid": "8,128",
  "best_candidate_attempts_per_second_estimate": 85000000,
  "grids": [
    {"step_size": 1024, "gpu_grid": "8,128", "candidate_attempts_per_second_estimate": 85000000}
  ]
}
JSON
cat >"$speed_sweep_dir/gpu_utilization.csv" <<'CSV'
timestamp, index, name, driver_version, utilization.gpu [%], utilization.memory [%], power.draw [W], memory.used [MiB], memory.total [MiB]
2026/06/18 00:00:00.000, 0, TEST_GPU, 555.0, 42 %, 5 %, 120 W, 1000 MiB, 80000 MiB
CSV
cat >"$speed_sweep_dir/build_step_1024.stdout.txt" <<'TXT'
ptxas info    : Used 64 registers, 320 bytes cmem[0]
TXT
python3 scripts/inspect_suffix_speed_sweep.py "$speed_sweep_dir" >/tmp/suffix_speed_sweep_low_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/suffix_speed_sweep_low_inspect.json").read_text())
assert data["decision"] == "increase_batch_or_fix_gpu_utilization", data["decision"]
assert data["meets_engineering_minimum"] is False
assert data["gpu_utilization"]["max_gpu_utilization_percent"] == 42.0
assert data["build_diagnostics"][0]["registers"] == 64
PY
cat >"$speed_sweep_dir/speed_sweep_summary.json" <<'JSON'
{
  "mode": "suffix_speed_sweep_summary",
  "passed": true,
  "best_step_size": 4096,
  "best_grid": "64,128",
  "best_candidate_attempts_per_second_estimate": 250000000,
  "grids": [
    {"step_size": 4096, "gpu_grid": "64,128", "candidate_attempts_per_second_estimate": 250000000}
  ]
}
JSON
cat >"$speed_sweep_dir/gpu_utilization.csv" <<'CSV'
timestamp, index, name, driver_version, utilization.gpu [%], utilization.memory [%], power.draw [W], memory.used [MiB], memory.total [MiB]
2026/06/18 00:00:00.000, 0, TEST_GPU, 555.0, 91 %, 30 %, 300 W, 1000 MiB, 80000 MiB
CSV
cat >"$speed_sweep_dir/build_step_4096.stdout.txt" <<'TXT'
ptxas info    : Used 72 registers, 0 bytes spill stores, 0 bytes spill loads, 384 bytes cmem[0]
TXT
python3 scripts/inspect_suffix_speed_sweep.py "$speed_sweep_dir" >/tmp/suffix_speed_sweep_min_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/suffix_speed_sweep_min_inspect.json").read_text())
assert data["decision"] == "engineering_min_passed_continue_toward_300m", data["decision"]
assert data["meets_engineering_minimum"] is True
assert data["meets_engineering_preferred"] is False
PY
cat >"$speed_sweep_dir/speed_sweep_summary.json" <<'JSON'
{
  "mode": "suffix_speed_sweep_summary",
  "passed": true,
  "best_step_size": 4096,
  "best_grid": "128,128",
  "best_candidate_attempts_per_second_estimate": 350000000,
  "grids": [
    {"step_size": 4096, "gpu_grid": "128,128", "candidate_attempts_per_second_estimate": 350000000}
  ]
}
JSON
python3 scripts/inspect_suffix_speed_sweep.py "$speed_sweep_dir" >/tmp/suffix_speed_sweep_preferred_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/suffix_speed_sweep_preferred_inspect.json").read_text())
assert data["decision"] == "preferred_speed_passed_profile_before_serverless", data["decision"]
assert data["meets_engineering_preferred"] is True
PY
sequence_dir="/tmp/tron_gpu_sequence_inspect_sample_$$"
mkdir -p "$sequence_dir"
cleanup_sequence_dir() {
    rm -f \
        "$sequence_dir/vector_gate.stdout.txt" \
        "$sequence_dir/smoke.stdout.txt" \
        "$sequence_dir/benchmark_3s.stdout.txt" \
        "$sequence_dir/benchmark_3s.inspect.json" \
        "$sequence_dir/benchmark_10s.stdout.txt" \
        "$sequence_dir/benchmark_10s.inspect.json"
    rmdir "$sequence_dir" 2>/dev/null || true
}
cleanup_result_inspector_dirs() {
    cleanup_serverless_find_dir
    cleanup_speed_sweep_dir
    cleanup_sequence_dir
}
trap cleanup_result_inspector_dirs EXIT
printf '%s\n' \
    "tron_gpu_address_layer_passed" \
    "tron_gpu_address_layer_script_passed" \
    "tron_gpu_vector_fields_verified" \
    >"$sequence_dir/vector_gate.stdout.txt"
printf '%s\n' "tron_gpu_pattern_smoke_passed" >"$sequence_dir/smoke.stdout.txt"
printf '%s\n' "tron_gpu_pattern_benchmark_passed" >"$sequence_dir/benchmark_3s.stdout.txt"
printf '%s\n' '{"passed": true, "failures": [], "summary": {"candidate_attempts_per_second_estimate": 800000000, "expected_mean_seconds": 0.82, "p90_seconds": 1.89, "single_worker_meets_goal": true, "required_workers": {"mean_5s": 1, "p90_8s": 1}}}' >"$sequence_dir/benchmark_3s.inspect.json"
python3 scripts/inspect_runpod_sequence_result.py "$sequence_dir" >/tmp/runpod_sequence_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/runpod_sequence_inspect.json").read_text())
assert data["decision"] == "run_10s_benchmark_next", data["decision"]
assert data["serverless_ready_speed_gate"] is False
PY
printf '%s\n' "tron_gpu_pattern_benchmark_passed" >"$sequence_dir/benchmark_10s.stdout.txt"
printf '%s\n' '{"passed": true, "failures": [], "summary": {"candidate_attempts_per_second_estimate": 85050000, "expected_mean_seconds": 7.72, "p90_seconds": 17.77, "single_worker_meets_goal": false, "required_workers": {"mean_5s": 2, "p90_8s": 3}}}' >"$sequence_dir/benchmark_10s.inspect.json"
python3 scripts/inspect_runpod_sequence_result.py "$sequence_dir" >/tmp/runpod_sequence_low_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/runpod_sequence_low_inspect.json").read_text())
assert data["decision"] == "optimize_cuda_before_serverless", data["decision"]
assert data["serverless_ready_speed_gate"] is False
PY
printf '%s\n' '{"passed": true, "failures": [], "summary": {"candidate_attempts_per_second_estimate": 250000000, "expected_mean_seconds": 2.63, "p90_seconds": 6.05, "single_worker_meets_goal": true, "required_workers": {"mean_5s": 1, "p90_8s": 1}}}' >"$sequence_dir/benchmark_10s.inspect.json"
python3 scripts/inspect_runpod_sequence_result.py "$sequence_dir" >/tmp/runpod_sequence_high_inspect.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/runpod_sequence_high_inspect.json").read_text())
assert data["decision"] == "speed_gate_passed_continue_profiling", data["decision"]
assert data["speed_gate_passed"] is True
assert data["serverless_ready_speed_gate"] is False
PY

echo "== vanitysearch patch gate"
python3 - <<'PY'
from hashlib import sha256
from pathlib import Path

patch = Path("patches/vanitysearch_tron_gpu_suffix_only_20260618.patch")
expected = "85aa5ab1eb2139fe0e3d762156b24d0ff742b56d3a7d111e0cc21f0420b261e6"
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
set +e
scripts/runpod_gpu_pod_suffix_speed_sweep.sh >/tmp/runpod_suffix_speed_sweep_gate_stdout.txt 2>/tmp/runpod_suffix_speed_sweep_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected RunPod suffix speed sweep script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi
set +e
scripts/runpod_gpu_pod_suffix_speed_test.sh >/tmp/runpod_suffix_speed_test_gate_stdout.txt 2>/tmp/runpod_suffix_speed_test_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected RunPod suffix speed test script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi
set +e
scripts/runpod_gpu_pod_find_debug.sh >/tmp/runpod_find_debug_gate_stdout.txt 2>/tmp/runpod_find_debug_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected RunPod find debug script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi
set +e
scripts/runpod_gpu_pod_suffix_compare_commits.sh >/tmp/runpod_suffix_compare_gate_stdout.txt 2>/tmp/runpod_suffix_compare_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected RunPod suffix compare script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi
set +e
scripts/build_vanitysearch_tron_worker.sh >/tmp/build_vanitysearch_tron_worker_gate_stdout.txt 2>/tmp/build_vanitysearch_tron_worker_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 2 ]; then
    echo "expected VanitySearch build script to refuse without env gate rc=2, got rc=$rc" >&2
    exit 1
fi
set +e
scripts/runpod_serverless_find_e2e.py >/tmp/runpod_serverless_find_e2e_gate_stdout.txt 2>/tmp/runpod_serverless_find_e2e_gate_stderr.txt
rc=$?
set -e
if [ "$rc" -ne 1 ]; then
    echo "expected Serverless find E2E runner to refuse without env gate rc=1, got rc=$rc" >&2
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
