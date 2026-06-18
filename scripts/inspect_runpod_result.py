#!/usr/bin/env python3
import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


FORBIDDEN_KEYS = {
    "private_key",
    "private_key_hex",
    "privateKey",
    "mnemonic",
    "seed",
    "token",
    "secret",
    "api_key",
    "apiKey",
}
BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

SEARCH_SPACE = 58 ** 5
ENGINEERING_MIN_ATTEMPTS_PER_SECOND = 200_000_000.0
ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND = 300_000_000.0
TARGETS = {
    "p50": 0.50,
    "p90": 0.90,
    "p95": 0.95,
    "p99": 0.99,
}


def load_json(path: str) -> Dict[str, Any]:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    return data


def unwrap_runpod(data: Dict[str, Any]) -> Dict[str, Any]:
    # RunPod /run status responses may wrap the handler response in output.
    output = data.get("output")
    if isinstance(output, dict):
        return output
    return data


def find_forbidden(obj: Any, path: str = "$") -> List[str]:
    hits: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_path = f"{path}.{key}"
            if key in FORBIDDEN_KEYS:
                hits.append(key_path)
            hits.extend(find_forbidden(value, key_path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            hits.extend(find_forbidden(value, f"{path}[{index}]"))
    return hits


def nested_get(obj: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def as_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"not a number: {value!r}")


def required_speed(probability: float, seconds: float = 10.0) -> float:
    return -math.log(1.0 - probability) * SEARCH_SPACE / seconds


def probability_for_speed(speed: float, seconds: float = 10.0) -> float:
    return 1.0 - math.exp(-(speed * seconds) / SEARCH_SPACE)


def inspect_validate(result: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    failures: List[str] = []
    if result.get("mode") != "validate_vectors":
        failures.append("mode is not validate_vectors")
    if nested_get(result, ["phase0_vectors", "passed"]) is not True:
        failures.append("phase0_vectors.passed is not true")
    if nested_get(result, ["compile", "ready"]) is not True:
        failures.append("compile.ready is not true")
    if nested_get(result, ["gpu_binary", "returncode"]) != 0:
        failures.append("gpu_binary.returncode is not 0")
    if result.get("passed") is not True:
        failures.append("passed is not true")
    return len(failures) == 0, failures, {
        "mode": result.get("mode"),
        "phase0_vectors_passed": nested_get(result, ["phase0_vectors", "passed"]),
        "compile_ready": nested_get(result, ["compile", "ready"]),
        "compile_elapsed_seconds": nested_get(result, ["compile", "elapsed_seconds"]),
        "gpu_binary_returncode": nested_get(result, ["gpu_binary", "returncode"]),
        "passed": result.get("passed"),
    }


def inspect_benchmark(result: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    failures: List[str] = []
    if result.get("mode") != "benchmark":
        failures.append("mode is not benchmark")
    benchmark = result.get("benchmark_result")
    if not isinstance(benchmark, dict):
        failures.append("benchmark_result is missing or not an object")
        benchmark = {}
    try:
        speed = as_float(benchmark.get("addresses_per_second"))
    except Exception:
        speed = 0.0
        failures.append("benchmark_result.addresses_per_second is missing or invalid")
    attempts = benchmark.get("attempts")
    if not isinstance(attempts, int) or attempts <= 0:
        failures.append("benchmark_result.attempts is not a positive integer")
    kernel_mode = benchmark.get("kernel_mode")
    if kernel_mode not in {"incremental_public_key_walk", "scalar_multiply_per_candidate"}:
        failures.append("benchmark_result.kernel_mode is not recognized")
    if not benchmark.get("gpu_name"):
        failures.append("benchmark_result.gpu_name is missing")
    if speed <= 0:
        failures.append("speed is not positive")

    p5 = probability_for_speed(speed, 5.0) if speed > 0 else 0.0
    p8 = probability_for_speed(speed, 8.0) if speed > 0 else 0.0
    workers = {}
    for label, probability in TARGETS.items():
        req = required_speed(probability, 8.0)
        workers[label] = math.ceil(req / speed) if speed > 0 else None
    required_mean_5s = SEARCH_SPACE / 5.0
    required_p90_8s = required_speed(0.90, 8.0)
    required_speed_to_meet_goal = max(
        required_mean_5s,
        required_p90_8s,
        ENGINEERING_MIN_ATTEMPTS_PER_SECOND,
    )

    return len(failures) == 0, failures, {
        "mode": result.get("mode"),
        "kernel_mode": kernel_mode,
        "gpu_name": benchmark.get("gpu_name"),
        "attempts": attempts,
        "addresses_per_second": speed,
        "keys_per_second": benchmark.get("keys_per_second"),
        "single_worker_probability_5s": p5,
        "single_worker_probability_8s": p8,
        "required_speed_for_mean_5s": required_mean_5s,
        "required_speed_for_p90_8s": required_p90_8s,
        "engineering_min_attempts_per_second": ENGINEERING_MIN_ATTEMPTS_PER_SECOND,
        "engineering_preferred_attempts_per_second": ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND,
        "required_speed_to_meet_goal": required_speed_to_meet_goal,
        "single_worker_meets_goal": speed >= required_speed_to_meet_goal if speed > 0 else False,
        "single_worker_meets_preferred_goal": speed >= ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND if speed > 0 else False,
        "required_workers_8s_probability_targets": workers,
        "matched": benchmark.get("matched"),
        "matched_address": benchmark.get("matched_address"),
    }


def inspect_find(result: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    failures: List[str] = []
    if result.get("mode") != "find":
        failures.append("mode is not find")
    if result.get("matched") is not True:
        failures.append("matched is not true")

    address = result.get("matched_address")
    if (
        not isinstance(address, str)
        or not address.startswith("T")
        or not 26 <= len(address) <= 40
        or any(ch not in BASE58_ALPHABET for ch in address)
    ):
        failures.append("matched_address is not a reasonable TRON Base58 address")

    match_rule = result.get("match_rule")
    suffix = None
    if isinstance(match_rule, dict):
        suffix = match_rule.get("suffix")
        if match_rule.get("prefix_len") != 0:
            failures.append("match_rule.prefix_len is not 0")
        if match_rule.get("suffix_len") != 5:
            failures.append("match_rule.suffix_len is not 5")
        if match_rule.get("search_space") != SEARCH_SPACE:
            failures.append("match_rule.search_space is not 58^5")
    else:
        failures.append("match_rule is missing or not an object")
    if not isinstance(suffix, str) or len(suffix) != 5:
        failures.append("match_rule.suffix is not exactly 5 chars")
    elif isinstance(address, str) and not address.endswith(suffix):
        failures.append("matched_address does not end with requested suffix")

    encrypted = result.get("encrypted_private_key")
    if not isinstance(encrypted, str) or not encrypted.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
        failures.append("encrypted_private_key is missing or is not age armor")

    return len(failures) == 0, failures, {
        "mode": result.get("mode"),
        "matched": result.get("matched"),
        "matched_address": address,
        "suffix": suffix,
        "gpu_worker_backend": result.get("gpu_worker_backend"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "has_age_ciphertext": isinstance(encrypted, str) and encrypted.startswith("-----BEGIN AGE ENCRYPTED FILE-----"),
        "response_keys": sorted(result.keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect RunPod validate/benchmark/find JSON response.")
    parser.add_argument("path", help="JSON file path, or '-' for stdin")
    parser.add_argument("--mode", choices=["auto", "validate_vectors", "benchmark", "find"], default="auto")
    args = parser.parse_args()

    data = load_json(args.path)
    forbidden = find_forbidden(data)
    result = unwrap_runpod(data)
    mode = args.mode if args.mode != "auto" else result.get("mode")

    if mode == "validate_vectors":
        passed, failures, summary = inspect_validate(result)
    elif mode == "benchmark":
        passed, failures, summary = inspect_benchmark(result)
    elif mode == "find":
        passed, failures, summary = inspect_find(result)
    else:
        passed, failures, summary = False, [f"unsupported or missing mode: {mode!r}"], {"mode": mode}

    if forbidden:
        failures.append("forbidden keys found: " + ", ".join(forbidden))
        passed = False

    print(json.dumps({
        "inspector": "runpod_result",
        "passed": passed,
        "mode": mode,
        "failures": failures,
        "forbidden_key_paths": forbidden,
        "summary": summary,
        "notes": [
            "This inspector does not call RunPod.",
            "Benchmark capacity uses product rule suffix=5 only; Python maps it to full-address prefix_len=0 + suffix_len=5 and search space is 58^5.",
            "Do not treat benchmark results as production proof until validate_vectors passes on RunPod.",
        ],
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
