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
EXPECTED_SEARCH_SPACE = 58 ** 6
EXPECTED_PREFIX_LEN = 2
EXPECTED_SUFFIX_LEN = 5
EXPECTED_PREFIX_AFTER_T_LEN = 1


def load_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def main() -> int:
    failures: list[str] = []

    capacity_globals: dict[str, object] = {}
    exec((ROOT / "scripts/capacity_math.py").read_text(encoding="utf-8"), capacity_globals)
    if capacity_globals.get("SEARCH_SPACE") != EXPECTED_SEARCH_SPACE:
        failures.append("capacity_math.SEARCH_SPACE must be 58^6 because leading T is fixed")

    inspector_globals: dict[str, object] = {}
    exec((ROOT / "scripts/inspect_runpod_result.py").read_text(encoding="utf-8"), inspector_globals)
    if inspector_globals.get("SEARCH_SPACE") != EXPECTED_SEARCH_SPACE:
        failures.append("inspect_runpod_result.SEARCH_SPACE must be 58^6 because leading T is fixed")

    contract = load_json("src/GPU_CORE_CONTRACT.json")
    default_rule = contract.get("default_rule", {})
    if default_rule.get("product_prefix_after_t_len") != EXPECTED_PREFIX_AFTER_T_LEN:
        failures.append("GPU_CORE_CONTRACT product_prefix_after_t_len must be 1")
    if default_rule.get("product_suffix_len") != EXPECTED_SUFFIX_LEN:
        failures.append("GPU_CORE_CONTRACT product_suffix_len must be 5")
    if default_rule.get("internal_full_address_prefix_len") != EXPECTED_PREFIX_LEN:
        failures.append("GPU_CORE_CONTRACT internal_full_address_prefix_len must be 2")
    if default_rule.get("internal_suffix_len") != EXPECTED_SUFFIX_LEN:
        failures.append("GPU_CORE_CONTRACT internal_suffix_len must be 5")

    for rel in PAYLOADS:
        payload = load_json(rel)
        input_payload = payload.get("input", {})
        prefix_after_t = input_payload.get("prefix_after_t")
        suffix = input_payload.get("suffix")
        if not isinstance(prefix_after_t, str) or len(prefix_after_t) != EXPECTED_PREFIX_AFTER_T_LEN:
            failures.append(f"{rel}: prefix_after_t must be exactly 1 character")
        if not isinstance(suffix, str) or len(suffix) != EXPECTED_SUFFIX_LEN:
            failures.append(f"{rel}: suffix must be exactly 5 characters")
        if "prefix_len" in input_payload or "suffix_len" in input_payload:
            failures.append(f"{rel}: product payload must use prefix_after_t/suffix, not prefix_len/suffix_len")

    result = {
        "mode": "validate_goal_rule",
        "passed": not failures,
        "failures": failures,
        "rule": {
            "full_address_prefix_len": EXPECTED_PREFIX_LEN,
            "product_prefix_after_t_len": EXPECTED_PREFIX_AFTER_T_LEN,
            "suffix_len": EXPECTED_SUFFIX_LEN,
            "fixed_leading_char": "T",
            "effective_variable_prefix_chars": 1,
            "effective_suffix_chars": EXPECTED_SUFFIX_LEN,
            "search_space": EXPECTED_SEARCH_SPACE,
            "search_space_formula": "58^6",
        },
        "notes": [
            "TRON leading T is fixed and must not be counted as a random Base58 character.",
            "Product payloads use prefix_after_t/suffix; Python maps them to full-address prefix_len=2/suffix_len=5 for the CUDA binary.",
            "This script does not call RunPod and does not run a benchmark.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
