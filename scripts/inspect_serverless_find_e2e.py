#!/usr/bin/env python3
"""Inspect repeated RunPod Serverless find responses for cold/warm E2E timing."""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RUNPOD_INSPECTOR_PATH = ROOT / "scripts" / "inspect_runpod_result.py"
AGE_VERIFIER_PATH = ROOT / "scripts" / "verify_age_encrypted_find_response.py"
TARGET_AVG_SECONDS = 5.0
TARGET_P90_SECONDS = 8.0
IGNORED_DIRECTORY_JSON_NAMES = {
    "manifest.json",
    "runpod_find_inspect.json",
    "serverless_find_e2e_inspect.json",
}


def load_runpod_inspector() -> Any:
    spec = importlib.util.spec_from_file_location("inspect_runpod_result", RUNPOD_INSPECTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load inspect_runpod_result.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_age_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("verify_age_encrypted_find_response", AGE_VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load verify_age_encrypted_find_response.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNPOD_INSPECTOR = load_runpod_inspector()
AGE_VERIFIER = load_age_verifier()


def load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"top-level JSON must be an object: {path}")
    return data


def candidate_paths(paths: List[str]) -> List[Path]:
    out: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in sorted(path.glob("*.json")):
                name = child.name.lower()
                if (
                    name in IGNORED_DIRECTORY_JSON_NAMES
                    or name.endswith("_inspect.json")
                    or name.endswith("_summary.json")
                ):
                    continue
                out.append(child)
        else:
            out.append(path)
    return out


def percentile(values: List[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * probability + 0.999999) - 1))
    return ordered[index]


def as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def latency_seconds(data: Dict[str, Any], output: Dict[str, Any]) -> float | None:
    for key in ("request_latency_seconds", "latency_seconds", "total_latency_seconds"):
        value = as_float(data.get(key))
        if value is not None:
            return value

    # RunPod responses vary by API path. executionTime is usually milliseconds.
    execution_time = as_float(data.get("executionTime"))
    if execution_time is not None:
        return execution_time / 1000.0 if execution_time > 100 else execution_time

    return as_float(output.get("elapsed_seconds"))


def inspect_one(path: Path, age_identity: Path | None, age_binary: str) -> Dict[str, Any]:
    data = load_json(path)
    forbidden = RUNPOD_INSPECTOR.find_forbidden(data)
    output = RUNPOD_INSPECTOR.unwrap_runpod(data)
    passed, failures, summary = RUNPOD_INSPECTOR.inspect_find(output)
    if forbidden:
        failures.append("forbidden keys found: " + ", ".join(forbidden))
        passed = False

    age_decrypt_passed = None
    if age_identity is not None:
        age_decrypt_passed = False
        if passed:
            try:
                decrypted = AGE_VERIFIER.decrypt_age(
                    output["encrypted_private_key"],
                    age_identity,
                    age_binary,
                )
                AGE_VERIFIER.require_hex_payload(decrypted)
                age_decrypt_passed = True
            except Exception as exc:
                failures.append(f"age envelope verification failed: {exc}")
                passed = False

    worker_elapsed = as_float(output.get("elapsed_seconds"))
    request_latency = latency_seconds(data, output)
    return {
        "path": str(path),
        "passed": passed,
        "failures": failures,
        "request_latency_seconds": request_latency,
        "worker_elapsed_seconds": worker_elapsed,
        "matched_address": summary.get("matched_address"),
        "suffix": summary.get("suffix"),
        "gpu_worker_backend": summary.get("gpu_worker_backend"),
        "has_age_ciphertext": summary.get("has_age_ciphertext"),
        "age_decrypt_passed": age_decrypt_passed,
    }


def summarize(samples: List[Dict[str, Any]], cold_count: int) -> Dict[str, Any]:
    failures: List[str] = []
    if not samples:
        failures.append("no response JSON files found")

    failed_samples = [sample for sample in samples if not sample["passed"]]
    if failed_samples:
        failures.append(f"{len(failed_samples)} sample(s) failed find response inspection")

    age_checked_samples = [
        sample for sample in samples if sample.get("age_decrypt_passed") is not None
    ]
    age_failed_samples = [
        sample for sample in age_checked_samples if sample.get("age_decrypt_passed") is not True
    ]
    if age_failed_samples:
        failures.append(f"{len(age_failed_samples)} sample(s) failed age envelope verification")

    latencies = [
        sample["request_latency_seconds"]
        for sample in samples
        if isinstance(sample.get("request_latency_seconds"), (int, float))
    ]
    if len(latencies) != len(samples):
        failures.append("one or more samples are missing request latency or worker elapsed timing")

    cold = samples[:cold_count] if cold_count > 0 else []
    warm = samples[cold_count:] if cold_count > 0 else samples
    warm_latencies = [
        sample["request_latency_seconds"]
        for sample in warm
        if isinstance(sample.get("request_latency_seconds"), (int, float))
    ]
    cold_latencies = [
        sample["request_latency_seconds"]
        for sample in cold
        if isinstance(sample.get("request_latency_seconds"), (int, float))
    ]
    warm_avg = statistics.fmean(warm_latencies) if warm_latencies else None
    warm_p90 = percentile(warm_latencies, 0.90)

    if len(warm) < 10:
        failures.append("need at least 10 warm samples for P90 evidence")
    if warm_avg is None or warm_avg > TARGET_AVG_SECONDS:
        failures.append("warm average latency does not meet <= 5s target")
    if warm_p90 is None or warm_p90 > TARGET_P90_SECONDS:
        failures.append("warm P90 latency does not meet <= 8s target")

    return {
        "mode": "inspect_serverless_find_e2e",
        "passed": not failures,
        "failures": failures,
        "sample_count": len(samples),
        "cold_count": len(cold),
        "warm_count": len(warm),
        "cold_latency_seconds": cold_latencies,
        "warm_average_seconds": warm_avg,
        "warm_p90_seconds": warm_p90,
        "age_decrypt_checked_count": len(age_checked_samples),
        "age_decrypt_passed_count": len(age_checked_samples) - len(age_failed_samples),
        "target_warm_average_seconds": TARGET_AVG_SECONDS,
        "target_warm_p90_seconds": TARGET_P90_SECONDS,
        "samples": samples,
        "notes": [
            "This inspector reads saved local JSON only.",
            "Use request_latency_seconds when available; otherwise it falls back to RunPod executionTime or worker elapsed_seconds.",
            "Cold start is reported separately and is not included in warm average/P90.",
            "If --age-identity is provided, age ciphertext is decrypted locally only to validate shape; decrypted key material is never printed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect repeated Serverless find responses.")
    parser.add_argument("paths", nargs="+", help="JSON response files or directories containing JSON files")
    parser.add_argument("--cold-count", type=int, default=1, help="Number of leading samples to treat as cold start")
    parser.add_argument("--age-identity", help="optional local test age identity for decrypt-shape verification")
    parser.add_argument("--age-binary", default="age", help="age binary path, default: age")
    args = parser.parse_args()

    paths = candidate_paths(args.paths)
    age_identity = Path(args.age_identity) if args.age_identity else None
    samples = [inspect_one(path, age_identity, args.age_binary) for path in paths]
    result = summarize(samples, max(0, args.cold_count))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
