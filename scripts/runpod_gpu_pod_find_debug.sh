#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_suffix_only_20260618.patch"
EXPECTED_PATCH_SHA="2c2ecf656c010ecb0ad4bc605ae0ef60cd91d77426340452675aeedf73210216"

if [ "${ALLOW_RUNPOD_FIND_DEBUG:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_FIND_DEBUG=1" >&2
  echo "This script is intended only for a short-lived normal RunPod GPU Pod." >&2
  echo "Do not run it on 47.80.70.211 or on a production server." >&2
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
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-tron-find-debug-$RUN_ID}"
RESULT_DIR="${RESULT_DIR:-$ROOT/runpod_results/find_debug_$RUN_ID}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CUDA_ARCH_INPUT="${CUDA_ARCH:-sm_120}"
CCAP="${CUDA_ARCH_INPUT#sm_}"
CXXCUDA="${CXXCUDA:-/usr/bin/g++}"
STEP_SIZE="${STEP_SIZE:-4096}"
BENCHMARK_SECONDS="${BENCHMARK_SECONDS:-3}"
BENCHMARK_GRID="${BENCHMARK_GRID:-128,128}"
BENCHMARK_PATTERN="${BENCHMARK_PATTERN:-T*CDEFG}"
FIND_SECONDS="${FIND_SECONDS:-5}"
FIND_GRID="${FIND_GRID:-1,128}"
FIND_DEBUG_SEED="${FIND_DEBUG_SEED:-codex-fixed-find-debug-20260618}"
PROBE_THREAD_INDEX="${PROBE_THREAD_INDEX:-0}"
PROBE_GPU_THREAD_ID="${PROBE_GPU_THREAD_ID:-128}"
PROBE_GROUP_SIZE="${PROBE_GROUP_SIZE:-1024}"
PROBE_INCR="${PROBE_INCR:-512}"

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

for value_name in BENCHMARK_SECONDS FIND_SECONDS PROBE_OFFSET; do
  value="${!value_name}"
  case "$value" in
    ''|*[!0-9]*)
      echo "$value_name must be an integer" >&2
      exit 1
      ;;
  esac
done
if [ "$BENCHMARK_SECONDS" -lt 1 ] || [ "$BENCHMARK_SECONDS" -gt 15 ]; then
  echo "BENCHMARK_SECONDS must be between 1 and 15" >&2
  exit 1
fi
if [ "$FIND_SECONDS" -lt 1 ] || [ "$FIND_SECONDS" -gt 15 ]; then
  echo "FIND_SECONDS must be between 1 and 15" >&2
  exit 1
fi
if ! [[ "$BENCHMARK_PATTERN" =~ ^T\*[1-9A-HJ-NP-Za-km-z]{5}$ ]]; then
  echo "BENCHMARK_PATTERN must be suffix-only format T*<five-base58-chars>" >&2
  exit 1
fi

if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi

mkdir -p "$WORKDIR" "$RESULT_DIR"

echo "== RunPod GPU Pod find debug"
echo "repo_commit=$(git -C "$ROOT" rev-parse HEAD)"
echo "cuda_arch=$CUDA_ARCH_INPUT"
echo "step_size=$STEP_SIZE"
echo "benchmark_seconds=$BENCHMARK_SECONDS"
echo "benchmark_grid=$BENCHMARK_GRID"
echo "find_seconds=$FIND_SECONDS"
echo "find_grid=$FIND_GRID"
echo "result_dir=$RESULT_DIR"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi >"$RESULT_DIR/nvidia_smi_initial.txt" 2>&1 || true
fi

echo "== clone VanitySearch candidate base"
git clone --quiet "$VANITYSEARCH_REPO" "$WORKDIR/VanitySearch"
cd "$WORKDIR/VanitySearch"
git checkout --quiet "$VANITYSEARCH_COMMIT"

for header in Timer.h hash/sha256.h hash/sha512.h; do
  if ! grep -q '#include <cstdint>' "$header"; then
    sed -i '/#include <string>/a #include <cstdint>' "$header"
  fi
done

echo "== apply TRON suffix-only patch"
git apply "$PATCH_PATH"

echo "== vector gate"
CUDA_ARCH="$CUDA_ARCH_INPUT" scripts/runpod_verify_tron_gpu_address_layer.sh \
  | tee "$RESULT_DIR/vector_gate.stdout.txt"
if ! grep -q "tron_gpu_address_layer_passed" "$RESULT_DIR/vector_gate.stdout.txt"; then
  echo "vector gate failed" >&2
  exit 1
fi

echo "== build VanitySearch STEP_SIZE=$STEP_SIZE"
make clean >/dev/null 2>&1 || true
make gpu=1 CCAP="$CCAP" CUDA="$CUDA_HOME" CXXCUDA="$CXXCUDA" STEP_SIZE="$STEP_SIZE" all \
  2>&1 | tee "$RESULT_DIR/build.stdout.txt"

echo "== short benchmark"
benchmark_stdout="$RESULT_DIR/benchmark.stdout.txt"
benchmark_stderr="$RESULT_DIR/benchmark.stderr.txt"
set +e
env TRON_SUPPRESS_SECRET_OUTPUT=1 timeout "${BENCHMARK_SECONDS}s" \
  ./VanitySearch -gpu -t 0 -g "$BENCHMARK_GRID" "$BENCHMARK_PATTERN" \
  >"$benchmark_stdout" 2>"$benchmark_stderr"
benchmark_rc=$?
set -e
if [ "$benchmark_rc" -ne 0 ] && [ "$benchmark_rc" -ne 124 ]; then
  echo "benchmark failed rc=$benchmark_rc" >&2
  tail -80 "$benchmark_stdout" >&2 || true
  tail -80 "$benchmark_stderr" >&2 || true
  exit 1
fi

python3 - "$benchmark_stdout" "$benchmark_stderr" "$benchmark_rc" "$BENCHMARK_SECONDS" "$BENCHMARK_GRID" "$RESULT_DIR/benchmark_summary.json" <<'PY'
from pathlib import Path
import json
import re
import sys

stdout_path, stderr_path, rc, seconds, grid, out_path = sys.argv[1:]
stdout = Path(stdout_path).read_text(errors="ignore")
stderr = Path(stderr_path).read_text(errors="ignore")
matches = re.findall(r"\[([0-9.]+) Mkey/s\]\[GPU ([0-9.]+) Mkey/s\]", stdout)
gpu_mkey_s = float(matches[-1][1]) if matches else None
summary = {
    "mode": "find_debug_short_benchmark",
    "passed": bool(matches),
    "return_code": int(rc),
    "timeout_reached": int(rc) == 124,
    "duration_seconds_limit": int(seconds),
    "gpu_grid": grid,
    "samples": len(matches),
    "reported_gpu_mkey_s": gpu_mkey_s,
    "candidate_attempts_per_second_estimate": gpu_mkey_s * 1_000_000.0 if gpu_mkey_s is not None else 0.0,
    "stderr_tail": stderr[-1000:],
}
Path(out_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
if not matches:
    raise SystemExit(1)
PY

echo "== derive fixed seed suffix"
probe_json="$RESULT_DIR/fixed_seed_probe.json"
./VanitySearch -ctg \
  "$FIND_DEBUG_SEED" \
  "$PROBE_THREAD_INDEX" \
  "$PROBE_GPU_THREAD_ID" \
  "$PROBE_GROUP_SIZE" \
  "$PROBE_INCR" \
  >"$probe_json"
suffix="$(python3 - "$probe_json" <<'PY'
from pathlib import Path
import json
import sys

data = json.loads(Path(sys.argv[1]).read_text())
suffix = data["suffix5"]
assert len(suffix) == 5
print(suffix)
PY
)"
echo "fixed_seed_probe_suffix=$suffix"

echo "== fixed seed must-hit GPU find"
find_stdout_raw="$RESULT_DIR/find_raw.stdout.txt"
find_stderr_raw="$RESULT_DIR/find_raw.stderr.txt"
set +e
env TRON_JSON_HIT_OUTPUT=1 TRON_SUPPRESS_SECRET_OUTPUT=1 TRON_DEBUG_FIND_RECHECK=1 \
  timeout "${FIND_SECONDS}s" \
  ./VanitySearch -gpu -stop -t 0 -g "$FIND_GRID" -s "$FIND_DEBUG_SEED" "T*$suffix" \
  >"$find_stdout_raw" 2>"$find_stderr_raw"
find_rc=$?
set -e
if [ "$find_rc" -ne 0 ] && [ "$find_rc" -ne 124 ]; then
  echo "find failed rc=$find_rc" >&2
  tail -120 "$find_stdout_raw" >&2 || true
  tail -120 "$find_stderr_raw" >&2 || true
  exit 1
fi

python3 - "$find_stdout_raw" "$find_stderr_raw" "$find_rc" "$FIND_SECONDS" "$FIND_GRID" "$suffix" "$RESULT_DIR/find_debug_summary.json" <<'PY'
from pathlib import Path
import json
import re
import sys

stdout_path, stderr_path, rc, seconds, grid, suffix, out_path = sys.argv[1:]
stdout = Path(stdout_path).read_text(errors="ignore")
stderr = Path(stderr_path).read_text(errors="ignore")
decoder = json.JSONDecoder()
hits = []
for index, char in enumerate(stdout):
    if char != "{":
        continue
    try:
        candidate, _ = decoder.raw_decode(stdout[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(candidate, dict) and candidate.get("mode") == "tron_find":
        hits.append(candidate)

matched = False
matched_address = None
if hits:
    last = hits[-1]
    matched = last.get("matched") is True and isinstance(last.get("matched_address"), str)
    matched_address = last.get("matched_address") if matched else None

debug_lines = [
    line for line in stdout.splitlines()
    if line.startswith("tron_debug_") or line.startswith("Warning, wrong private key generated")
]
summary = {
    "mode": "fixed_seed_find_debug",
    "passed": bool(matched and matched_address.endswith(suffix)),
    "return_code": int(rc),
    "timeout_reached": int(rc) == 124,
    "duration_seconds_limit": int(seconds),
    "gpu_grid": grid,
    "target_suffix": suffix,
    "json_hit_count": len(hits),
    "matched": matched,
    "matched_address": matched_address,
    "matched_suffix_ok": bool(matched_address and matched_address.endswith(suffix)),
    "debug_lines": debug_lines[-40:],
    "stderr_tail": stderr[-1000:],
    "notes": [
        "Raw stdout may contain an internal test-only key value; do not paste it into chat.",
        "The summary intentionally omits any internal key value.",
    ],
}
Path(out_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
if not summary["passed"]:
    raise SystemExit(1)
PY

rm -f "$find_stdout_raw"
printf '%s\n' "raw find stdout erased after sanitized summary" \
  >"$RESULT_DIR/find_raw_stdout_erased.txt"

echo "runpod_gpu_pod_find_debug_complete"
