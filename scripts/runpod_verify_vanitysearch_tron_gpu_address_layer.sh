#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_PATH="$ROOT/patches/vanitysearch_tron_gpu_suffix_only_20260618.patch"

if [ "${ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK:-0}" != "1" ]; then
  echo "refusing_to_run_without_ALLOW_RUNPOD_VANITYSEARCH_GPU_CHECK=1" >&2
  echo "This script is intended for a short-lived CUDA RunPod Pod only." >&2
  exit 2
fi

if [ ! -f "$PATCH_PATH" ]; then
  echo "missing patch: $PATCH_PATH" >&2
  exit 1
fi

EXPECTED_SHA="85aa5ab1eb2139fe0e3d762156b24d0ff742b56d3a7d111e0cc21f0420b261e6"
ACTUAL_SHA="$(sha256sum "$PATCH_PATH" | awk '{print $1}')"
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
  echo "patch sha256 mismatch" >&2
  echo "expected=$EXPECTED_SHA" >&2
  echo "actual=$ACTUAL_SHA" >&2
  exit 1
fi

VANITYSEARCH_REPO="${VANITYSEARCH_REPO:-https://github.com/JeanLucPons/VanitySearch.git}"
VANITYSEARCH_COMMIT="${VANITYSEARCH_COMMIT:-c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b}"
WORKDIR="${WORKDIR:-/tmp/vanitysearch-tron-gpu-address-layer-$(date +%s)}"
CUDA_ARCH="${CUDA_ARCH:-sm_80}"

if [ -e "$WORKDIR" ]; then
  echo "workdir already exists, refusing to overwrite: $WORKDIR" >&2
  exit 1
fi
mkdir -p "$WORKDIR"

echo "== clone VanitySearch candidate base"
git clone --quiet "$VANITYSEARCH_REPO" "$WORKDIR/VanitySearch"
cd "$WORKDIR/VanitySearch"
git checkout --quiet "$VANITYSEARCH_COMMIT"

echo "== apply TRON GPU address layer patch"
git apply "$PATCH_PATH"

echo "== run GPU TRON address layer vector check"
VECTOR_STDOUT="$WORKDIR/tron_gpu_address_layer_stdout.txt"
CUDA_ARCH="$CUDA_ARCH" scripts/runpod_verify_tron_gpu_address_layer.sh | tee "$VECTOR_STDOUT"

echo "== verify GPU TRON vector fields"
python3 - "$VECTOR_STDOUT" <<'PY'
import json
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
decoder = json.JSONDecoder()
data = None
for index, char in enumerate(text):
    if char != "{":
        continue
    try:
        candidate, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(candidate, dict) and candidate.get("mode") == "tron_gpu_address_layer_vectors":
        data = candidate
        break

if data is None:
    raise SystemExit("missing tron_gpu_address_layer_vectors JSON")

required_fields = [
    "passed",
    "match_rule_passed",
    "wrong_rule_rejected",
    "suffix_prefilter_passed",
    "wrong_suffix_prefilter_rejected",
    "suffix_fast_prefilter_passed",
    "wrong_suffix_fast_prefilter_rejected",
    "suffix_checksum_word_prefilter_passed",
    "wrong_suffix_checksum_word_prefilter_rejected",
    "xy_payload_passed",
]

results = data.get("results")
if not isinstance(results, list) or len(results) < 4:
    raise SystemExit("expected at least 4 public TEST_ONLY vector results")

failures = []
for item in results:
    if not isinstance(item, dict):
        failures.append("non-object result")
        continue
    index = item.get("index")
    for field in required_fields:
        if item.get(field) is not True:
            failures.append(f"vector {index}: {field} is not true")

if data.get("passed") != len(results) or data.get("failed") != 0:
    failures.append("summary passed/failed counts do not match all vectors")

if failures:
    raise SystemExit("; ".join(failures))

print("tron_gpu_vector_fields_verified")
PY

if [ "${RUN_TRON_PATTERN_SMOKE:-0}" = "1" ]; then
  echo "== run optional TRON GPU pattern search smoke"
  ALLOW_RUNPOD_TRON_GPU_PATTERN_SMOKE=1 CUDA_ARCH="${CUDA_ARCH#sm_}" \
    bash scripts/runpod_tron_gpu_pattern_search_smoke.sh
fi

if [ "${RUN_TRON_PATTERN_BENCHMARK:-0}" = "1" ]; then
  echo "== run optional bounded TRON GPU pattern benchmark"
  ALLOW_RUNPOD_TRON_GPU_PATTERN_BENCHMARK=1 CUDA_ARCH="${CUDA_ARCH#sm_}" \
    bash scripts/runpod_tron_gpu_pattern_benchmark.sh
fi
