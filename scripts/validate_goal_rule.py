#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = [
    "RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json",
    "RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_FIND_SAMPLE_PAYLOAD.json",
]
CURRENT_DOCS = [
    "docs/BUILD_AND_RUNPOD_GATE.md",
    "docs/FINAL_GOAL_ACCEPTANCE_GATE.md",
    "docs/RUNPOD_SERVERLESS_FIND_E2E_NEXT.md",
    "docs/SERVERLESS_MIGRATION_GAP_AFTER_SUFFIX_SPEED.md",
]
FORBIDDEN_CURRENT_DOC_MARKERS = [
    '"prefix_len": 2',
    "prefix_len = 2",
    "prefix_after_t + suffix5",
    "Suffix-only hot path and benchmark gate still need to be updated and retested",
    "Run a low-cost x86 Linux RunPod Pod check",
    "tron_cpu_vectors_passed",
]
EXPECTED_SEARCH_SPACE = 58 ** 5
EXPECTED_PREFIX_LEN = 0
EXPECTED_SUFFIX_LEN = 5


def load_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def main() -> int:
    failures: list[str] = []

    capacity_globals: dict[str, object] = {}
    exec((ROOT / "scripts/capacity_math.py").read_text(encoding="utf-8"), capacity_globals)
    if capacity_globals.get("SEARCH_SPACE") != EXPECTED_SEARCH_SPACE:
        failures.append("capacity_math.SEARCH_SPACE must be 58^5 for suffix-only matching")

    inspector_globals: dict[str, object] = {}
    exec((ROOT / "scripts/inspect_runpod_result.py").read_text(encoding="utf-8"), inspector_globals)
    if inspector_globals.get("SEARCH_SPACE") != EXPECTED_SEARCH_SPACE:
        failures.append("inspect_runpod_result.SEARCH_SPACE must be 58^5 for suffix-only matching")

    contract = load_json("src/GPU_CORE_CONTRACT.json")
    default_rule = contract.get("default_rule", {})
    if default_rule.get("product_prefix_after_t_len") != 0:
        failures.append("GPU_CORE_CONTRACT product_prefix_after_t_len must be 0")
    if default_rule.get("product_suffix_len") != EXPECTED_SUFFIX_LEN:
        failures.append("GPU_CORE_CONTRACT product_suffix_len must be 5")
    if default_rule.get("internal_full_address_prefix_len") != EXPECTED_PREFIX_LEN:
        failures.append("GPU_CORE_CONTRACT internal_full_address_prefix_len must be 0")
    if default_rule.get("internal_suffix_len") != EXPECTED_SUFFIX_LEN:
        failures.append("GPU_CORE_CONTRACT internal_suffix_len must be 5")

    for rel in PAYLOADS:
        payload = load_json(rel)
        input_payload = payload.get("input", {})
        suffix = input_payload.get("suffix")
        if "prefix_after_t" in input_payload:
            failures.append(f"{rel}: prefix_after_t must not be present for suffix-only product payloads")
        if not isinstance(suffix, str) or len(suffix) != EXPECTED_SUFFIX_LEN:
            failures.append(f"{rel}: suffix must be exactly 5 characters")
        if "prefix_len" in input_payload or "suffix_len" in input_payload:
            failures.append(f"{rel}: product payload must use suffix, not prefix_len/suffix_len")

    for rel in CURRENT_DOCS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in FORBIDDEN_CURRENT_DOC_MARKERS:
            if marker in text:
                failures.append(f"{rel}: stale product-rule marker found: {marker}")

    result = {
        "mode": "validate_goal_rule",
        "passed": not failures,
        "failures": failures,
        "rule": {
            "full_address_prefix_len": EXPECTED_PREFIX_LEN,
            "product_prefix_after_t_len": 0,
            "suffix_len": EXPECTED_SUFFIX_LEN,
            "fixed_leading_char": "T",
            "effective_variable_prefix_chars": 0,
            "effective_suffix_chars": EXPECTED_SUFFIX_LEN,
            "search_space": EXPECTED_SEARCH_SPACE,
            "search_space_formula": "58^5",
        },
        "notes": [
            "Product payloads use suffix only; no prefix after fixed T is matched.",
            "Python maps suffix-only input to full-address prefix_len=0/suffix_len=5 for the CUDA binary.",
            "This script does not call RunPod and does not run a benchmark.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
