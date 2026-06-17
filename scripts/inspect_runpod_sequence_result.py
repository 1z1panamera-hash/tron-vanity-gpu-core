#!/usr/bin/env python3
"""Inspect a runpod_gpu_pod_sequence.sh result directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_SPEED_MEAN_5S = 131_271_353.6
REQUIRED_SPEED_P90_8S = 188_914_663.71031892
REQUIRED_SPEED_TO_MEET_GOAL = REQUIRED_SPEED_P90_8S

MARKERS = {
    "vector_gate": [
        "tron_gpu_address_layer_passed",
        "tron_gpu_address_layer_script_passed",
        "tron_gpu_vector_fields_verified",
    ],
    "smoke": [
        "tron_gpu_pattern_smoke_passed",
    ],
    "benchmark_3s": [
        "tron_gpu_pattern_benchmark_passed",
    ],
    "benchmark_10s": [
        "tron_gpu_pattern_benchmark_passed",
    ],
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def marker_status(result_dir: Path, step: str) -> Dict[str, Any]:
    stdout_path = result_dir / f"{step}.stdout.txt"
    text = read_text(stdout_path)
    markers = MARKERS[step]
    return {
        "step": step,
        "stdout_path": str(stdout_path),
        "present": stdout_path.exists(),
        "markers": {marker: marker in text for marker in markers},
        "passed": stdout_path.exists() and all(marker in text for marker in markers),
    }


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def benchmark_summary(result_dir: Path, step: str) -> Dict[str, Any]:
    inspect_path = result_dir / f"{step}.inspect.json"
    data = load_json(inspect_path)
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    speed = summary.get("candidate_attempts_per_second_estimate")
    meets_goal = (
        isinstance(speed, (int, float)) and
        float(speed) >= REQUIRED_SPEED_TO_MEET_GOAL and
        summary.get("single_worker_meets_goal") is True
    )
    return {
        "step": step,
        "inspect_path": str(inspect_path),
        "present": inspect_path.exists(),
        "passed": data.get("passed") is True,
        "candidate_attempts_per_second_estimate": summary.get("candidate_attempts_per_second_estimate"),
        "expected_mean_seconds": summary.get("expected_mean_seconds"),
        "p90_seconds": summary.get("p90_seconds"),
        "single_worker_meets_goal": summary.get("single_worker_meets_goal"),
        "meets_suffix_only_speed_goal": meets_goal,
        "required_speed_for_mean_5s": REQUIRED_SPEED_MEAN_5S,
        "required_speed_for_p90_8s": REQUIRED_SPEED_P90_8S,
        "required_workers": summary.get("required_workers"),
        "failures": data.get("failures", []),
    }


def inspect_sequence(result_dir: Path) -> Dict[str, Any]:
    failures: List[str] = []
    steps = {step: marker_status(result_dir, step) for step in MARKERS}
    benchmarks = {
        "benchmark_3s": benchmark_summary(result_dir, "benchmark_3s"),
        "benchmark_10s": benchmark_summary(result_dir, "benchmark_10s"),
    }

    if not steps["vector_gate"]["passed"]:
        failures.append("vector gate missing or failed")

    if steps["smoke"]["present"] and not steps["smoke"]["passed"]:
        failures.append("smoke output exists but required marker is missing")

    for step in ("benchmark_3s", "benchmark_10s"):
        if steps[step]["present"] and not steps[step]["passed"]:
            failures.append(f"{step} output exists but benchmark marker is missing")
        if steps[step]["present"] and not benchmarks[step]["passed"]:
            failures.append(f"{step} inspector missing or failed")

    serverless_ready_speed_gate = False
    decision = "run_vector_gate_first"
    if steps["benchmark_10s"]["passed"] and benchmarks["benchmark_10s"]["passed"]:
        if benchmarks["benchmark_10s"]["meets_suffix_only_speed_goal"]:
            serverless_ready_speed_gate = True
            decision = "serverless_speed_gate_passed_pending_find_validation"
        else:
            decision = "optimize_cuda_before_serverless"
    elif steps["vector_gate"]["passed"] and not steps["smoke"]["present"]:
        decision = "run_smoke_next"
    elif steps["smoke"]["passed"] and not steps["benchmark_3s"]["present"]:
        decision = "run_3s_benchmark_next"
    elif steps["benchmark_3s"]["passed"] and benchmarks["benchmark_3s"]["passed"] and not steps["benchmark_10s"]["present"]:
        decision = "run_10s_benchmark_next"
    if failures:
        decision = "stop_and_review_failures"

    return {
        "mode": "inspect_runpod_sequence_result",
        "result_dir": str(result_dir),
        "passed": not failures,
        "serverless_ready_speed_gate": serverless_ready_speed_gate,
        "decision": decision,
        "failures": failures,
        "steps": steps,
        "benchmarks": benchmarks,
        "notes": [
            "This inspector reads local result files only.",
            "It does not call RunPod, compile CUDA, or run benchmarks.",
            "Suffix-only speed target is mean <= 5s and P90 <= 8s, requiring about 188.91M complete TRON addresses/s for one worker.",
            "Serverless migration still requires real GPU Pod evidence and age-encrypted find validation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect runpod_gpu_pod_sequence.sh output directory.")
    parser.add_argument("result_dir", help="Path to runpod_results/<run-id>")
    args = parser.parse_args()
    result = inspect_sequence(Path(args.result_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
