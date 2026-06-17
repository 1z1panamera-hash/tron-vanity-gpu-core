#!/usr/bin/env python3
"""Inspect bounded VanitySearch TRON GPU pattern benchmark output.

This parser accepts either a pure JSON file or the mixed stdout produced by the
RunPod helper script, then estimates whether the measured candidate rate can
meet the product rule target. It does not call RunPod and does not run CUDA.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


SEARCH_SPACE = 58 ** 6
MEAN_TARGET_SECONDS = 10.0
P90_TARGET_SECONDS = 15.0
FORBIDDEN_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bPriv\b",
        r"\bWIF\b",
        r"\bHEX\b",
        r"private_key",
        r"mnemonic",
        r"\bseed\b",
        r"\btoken\b",
        r"\bsecret\b",
    ]
]


def load_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            data, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("mode") == "tron_gpu_pattern_benchmark":
            return data
    raise ValueError("could not find tron_gpu_pattern_benchmark JSON object")


def forbidden_hits(text: str) -> List[str]:
    text = text.replace("TRON_SUPPRESS_SECRET_OUTPUT", "TRON_SUPPRESS_OUTPUT")
    hits: List[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def as_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"not a number: {value!r}")


def required_speed_for_probability(probability: float, seconds: float) -> float:
    return -math.log(1.0 - probability) * SEARCH_SPACE / seconds


def probability_for_speed(speed: float, seconds: float) -> float:
    return 1.0 - math.exp(-(speed * seconds) / SEARCH_SPACE)


def inspect(data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    failures: List[str] = []
    hits = forbidden_hits(raw_text)
    if hits:
        failures.append("forbidden sensitive marker found in raw output: " + ", ".join(hits))

    if data.get("mode") != "tron_gpu_pattern_benchmark":
        failures.append("mode is not tron_gpu_pattern_benchmark")
    if data.get("passed") is not True:
        failures.append("passed is not true")
    if data.get("pattern") and not re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]\*[1-9A-HJ-NP-Za-km-z]{5}", str(data["pattern"])):
        failures.append("pattern does not match T<one-base58>*<five-base58>")

    try:
        speed = as_float(data.get("candidate_attempts_per_second_estimate"))
    except Exception:
        speed = 0.0
        failures.append("candidate_attempts_per_second_estimate is missing or invalid")

    if speed <= 0:
        failures.append("candidate_attempts_per_second_estimate is not positive")

    duration_limit = data.get("duration_seconds_limit")
    if not isinstance(duration_limit, int) or duration_limit < 3 or duration_limit > 30:
        failures.append("duration_seconds_limit is not an integer in 3..30")

    mean_seconds = SEARCH_SPACE / speed if speed > 0 else None
    p90_seconds = required_speed_for_probability(0.90, 1.0) / speed if speed > 0 else None
    required_mean_speed = SEARCH_SPACE / MEAN_TARGET_SECONDS
    required_p90_speed = required_speed_for_probability(0.90, P90_TARGET_SECONDS)
    required_speed = max(required_mean_speed, required_p90_speed)

    required_workers = {
        "mean_10s": math.ceil(required_mean_speed / speed) if speed > 0 else None,
        "p90_15s": math.ceil(required_p90_speed / speed) if speed > 0 else None,
    }

    return {
        "inspector": "vanitysearch_bounded_benchmark",
        "passed": not failures,
        "failures": failures,
        "forbidden_marker_patterns": hits,
        "summary": {
            "pattern": data.get("pattern"),
            "reported_gpu_mkey_s": data.get("reported_gpu_mkey_s"),
            "candidate_attempts_per_second_estimate": speed,
            "search_space": SEARCH_SPACE,
            "single_worker_probability_10s": probability_for_speed(speed, 10.0) if speed > 0 else 0.0,
            "single_worker_probability_15s": probability_for_speed(speed, 15.0) if speed > 0 else 0.0,
            "expected_mean_seconds": mean_seconds,
            "p90_seconds": p90_seconds,
            "required_speed_for_mean_10s": required_mean_speed,
            "required_speed_for_p90_15s": required_p90_speed,
            "required_speed_to_meet_goal": required_speed,
            "single_worker_meets_goal": bool(speed >= required_speed) if speed > 0 else False,
            "required_workers": required_workers,
        },
        "notes": [
            "This only inspects local text/JSON; it does not call RunPod.",
            "The target space is 58^6 because TRON leading T is fixed.",
            "Use benchmark output from the corrected TRON counter patch; older VanitySearch TRON Mkey/s can be 6x inflated.",
            "This bounded VanitySearch signal is not final Serverless P90 proof.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect bounded VanitySearch TRON GPU benchmark output.")
    parser.add_argument("path", help="Path to benchmark stdout/JSON, or '-' for stdin")
    args = parser.parse_args()

    raw = load_text(args.path)
    data = extract_json_object(raw)
    result = inspect(data, raw)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
