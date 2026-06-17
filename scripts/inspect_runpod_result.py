#!/usr/bin/env python3
import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


FORBIDDEN_KEYS = {
    "private_key",
    "privateKey",
    "mnemonic",
    "seed",
    "token",
    "secret",
    "api_key",
    "apiKey",
}

SEARCH_SPACE = 58 ** 6
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

    p10 = probability_for_speed(speed, 10.0) if speed > 0 else 0.0
    workers = {}
    for label, probability in TARGETS.items():
        req = required_speed(probability, 10.0)
        workers[label] = math.ceil(req / speed) if speed > 0 else None

    return len(failures) == 0, failures, {
        "mode": result.get("mode"),
        "kernel_mode": kernel_mode,
        "gpu_name": benchmark.get("gpu_name"),
        "attempts": attempts,
        "addresses_per_second": speed,
        "keys_per_second": benchmark.get("keys_per_second"),
        "single_worker_probability_10s": p10,
        "required_workers_10s": workers,
        "matched": benchmark.get("matched"),
        "matched_address": benchmark.get("matched_address"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect RunPod validate/benchmark JSON response.")
    parser.add_argument("path", help="JSON file path, or '-' for stdin")
    parser.add_argument("--mode", choices=["auto", "validate_vectors", "benchmark"], default="auto")
    args = parser.parse_args()

    data = load_json(args.path)
    forbidden = find_forbidden(data)
    result = unwrap_runpod(data)
    mode = args.mode if args.mode != "auto" else result.get("mode")

    if mode == "validate_vectors":
        passed, failures, summary = inspect_validate(result)
    elif mode == "benchmark":
        passed, failures, summary = inspect_benchmark(result)
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
            "Benchmark capacity uses full TRON Base58 prefix_len=2 + suffix_len=5, with fixed leading T, so search space is 58^6.",
            "Do not treat benchmark results as production proof until validate_vectors passes on RunPod.",
        ],
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
