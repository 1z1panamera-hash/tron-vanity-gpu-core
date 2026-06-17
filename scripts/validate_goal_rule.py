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
]
EXPECTED_SEARCH_SPACE = 58 ** 6
EXPECTED_PREFIX_LEN = 2
EXPECTED_SUFFIX_LEN = 5


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
    if default_rule.get("prefix_len") != EXPECTED_PREFIX_LEN:
        failures.append("GPU_CORE_CONTRACT default prefix_len must be 2 on full TRON address")
    if default_rule.get("suffix_len") != EXPECTED_SUFFIX_LEN:
        failures.append("GPU_CORE_CONTRACT default suffix_len must be 5")

    for rel in PAYLOADS:
        payload = load_json(rel)
        input_payload = payload.get("input", {})
        address = input_payload.get("target_address", "")
        if not isinstance(address, str) or not address.startswith("T"):
            failures.append(f"{rel}: target_address must start with fixed TRON T")
        if input_payload.get("prefix_len") != EXPECTED_PREFIX_LEN:
            failures.append(f"{rel}: prefix_len must be 2, including fixed leading T")
        if input_payload.get("suffix_len") != EXPECTED_SUFFIX_LEN:
            failures.append(f"{rel}: suffix_len must be 5")
        if isinstance(address, str) and input_payload.get("prefix_len") == EXPECTED_PREFIX_LEN:
            variable_prefix = address[1:EXPECTED_PREFIX_LEN]
            if len(variable_prefix) != 1:
                failures.append(f"{rel}: effective variable prefix after T must be exactly 1 char")

    result = {
        "mode": "validate_goal_rule",
        "passed": not failures,
        "failures": failures,
        "rule": {
            "full_address_prefix_len": EXPECTED_PREFIX_LEN,
            "suffix_len": EXPECTED_SUFFIX_LEN,
            "fixed_leading_char": "T",
            "effective_variable_prefix_chars": 1,
            "effective_suffix_chars": EXPECTED_SUFFIX_LEN,
            "search_space": EXPECTED_SEARCH_SPACE,
            "search_space_formula": "58^6",
        },
        "notes": [
            "TRON leading T is fixed and must not be counted as a random Base58 character.",
            "Runtime payloads still use prefix_len=2 because matching is against the full TRON Base58 address.",
            "This script does not call RunPod and does not run a benchmark.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
