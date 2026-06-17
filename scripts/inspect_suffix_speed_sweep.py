#!/usr/bin/env python3
"""Inspect a RunPod suffix speed sweep result directory.

This reads files produced by runpod_gpu_pod_suffix_speed_sweep.sh. It does not
call RunPod, run CUDA, or compile anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List


ENGINEERING_MIN_ATTEMPTS_PER_SECOND = 200_000_000.0
ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND = 300_000_000.0
LOW_GPU_UTILIZATION_PERCENT = 80.0


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def as_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0


def inspect_gpu_utilization(result_dir: Path, summary: Dict[str, Any]) -> Dict[str, Any]:
    embedded = summary.get("gpu_utilization")
    if isinstance(embedded, dict) and embedded.get("samples"):
        return embedded

    util_path = result_dir / "gpu_utilization.csv"
    samples: List[float] = []
    if util_path.exists():
        with util_path.open(newline="", errors="ignore") as handle:
            for row in csv.reader(handle):
                if not row or row[0].strip().lower() == "timestamp":
                    continue
                if len(row) < 5:
                    continue
                match = re.search(r"([0-9.]+)", row[4])
                if match:
                    samples.append(float(match.group(1)))

    return {
        "path": str(util_path),
        "present": util_path.exists(),
        "samples": len(samples),
        "avg_gpu_utilization_percent": sum(samples) / len(samples) if samples else None,
        "max_gpu_utilization_percent": max(samples) if samples else None,
    }


def inspect_build_diagnostics(result_dir: Path) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    for path in sorted(result_dir.glob("build_step_*.stdout.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        step_match = re.search(r"build_step_([0-9]+)\.stdout\.txt$", path.name)
        item: Dict[str, Any] = {
            "path": str(path),
            "step_size": int(step_match.group(1)) if step_match else None,
            "registers": None,
            "spill_stores_bytes": 0,
            "spill_loads_bytes": 0,
            "shared_memory_bytes": None,
            "constant_memory_bytes": None,
            "ptxas_lines": [],
        }
        for line in text.splitlines():
            if "ptxas" not in line:
                continue
            item["ptxas_lines"].append(line)
            reg_match = re.search(r"Used\s+([0-9]+)\s+registers", line)
            if reg_match:
                item["registers"] = int(reg_match.group(1))
            smem_match = re.search(r"([0-9]+)\s+bytes\s+smem", line)
            if smem_match:
                item["shared_memory_bytes"] = int(smem_match.group(1))
            cmem_match = re.search(r"([0-9]+)\s+bytes\s+cmem", line)
            if cmem_match:
                item["constant_memory_bytes"] = int(cmem_match.group(1))
            spill_store_match = re.search(r"([0-9]+)\s+bytes\s+spill stores", line)
            if spill_store_match:
                item["spill_stores_bytes"] += int(spill_store_match.group(1))
            spill_load_match = re.search(r"([0-9]+)\s+bytes\s+spill loads", line)
            if spill_load_match:
                item["spill_loads_bytes"] += int(spill_load_match.group(1))
        diagnostics.append(item)
    return diagnostics


def inspect(result_dir: Path) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    summary_path = result_dir / "speed_sweep_summary.json"
    summary = load_json(summary_path)

    if not summary:
        failures.append("speed_sweep_summary.json is missing or invalid")

    if summary.get("mode") != "suffix_speed_sweep_summary":
        failures.append("summary mode is not suffix_speed_sweep_summary")

    best_speed = as_float(summary.get("best_candidate_attempts_per_second_estimate"))
    best_step_size = summary.get("best_step_size")
    best_grid = summary.get("best_grid")
    if best_speed <= 0:
        failures.append("best speed is missing or not positive")
    if best_step_size is None:
        failures.append("best_step_size is missing")
    if not best_grid:
        failures.append("best_grid is missing")

    grid_results = summary.get("grids")
    if not isinstance(grid_results, list) or not grid_results:
        failures.append("grid results are missing")

    gpu_util = inspect_gpu_utilization(result_dir, summary)
    build_diagnostics = inspect_build_diagnostics(result_dir)
    max_util = gpu_util.get("max_gpu_utilization_percent")
    avg_util = gpu_util.get("avg_gpu_utilization_percent")
    if not gpu_util.get("present"):
        warnings.append("gpu_utilization.csv is missing")
    elif not gpu_util.get("samples"):
        warnings.append("gpu utilization samples are missing")
    elif isinstance(max_util, (int, float)) and max_util < LOW_GPU_UTILIZATION_PERCENT:
        warnings.append("GPU utilization is low; increase STEP_SIZE/grid or inspect occupancy")
    if not build_diagnostics:
        warnings.append("build_step_<STEP_SIZE>.stdout.txt files are missing")
    for item in build_diagnostics:
        if item.get("spill_stores_bytes") or item.get("spill_loads_bytes"):
            warnings.append(
                f"ptxas spill detected for STEP_SIZE={item.get('step_size')}: "
                f"stores={item.get('spill_stores_bytes')} loads={item.get('spill_loads_bytes')}"
            )

    meets_min = best_speed >= ENGINEERING_MIN_ATTEMPTS_PER_SECOND
    meets_preferred = best_speed >= ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND

    decision = "stop_and_review_failures"
    if not failures:
        if meets_preferred:
            decision = "preferred_speed_passed_profile_before_serverless"
        elif meets_min:
            decision = "engineering_min_passed_continue_toward_300m"
        elif isinstance(max_util, (int, float)) and max_util < LOW_GPU_UTILIZATION_PERCENT:
            decision = "increase_batch_or_fix_gpu_utilization"
        else:
            decision = "optimize_secp256k1_or_address_hot_path"

    return {
        "mode": "inspect_suffix_speed_sweep",
        "result_dir": str(result_dir),
        "summary_path": str(summary_path),
        "passed": not failures,
        "decision": decision,
        "failures": failures,
        "warnings": warnings,
        "best_step_size": best_step_size,
        "best_grid": best_grid,
        "best_candidate_attempts_per_second_estimate": best_speed,
        "engineering_min_attempts_per_second": ENGINEERING_MIN_ATTEMPTS_PER_SECOND,
        "engineering_preferred_attempts_per_second": ENGINEERING_PREFERRED_ATTEMPTS_PER_SECOND,
        "meets_engineering_minimum": meets_min,
        "meets_engineering_preferred": meets_preferred,
        "gpu_utilization": {
            "present": gpu_util.get("present"),
            "samples": gpu_util.get("samples"),
            "avg_gpu_utilization_percent": avg_util,
            "max_gpu_utilization_percent": max_util,
            "low_utilization_threshold_percent": LOW_GPU_UTILIZATION_PERCENT,
        },
        "build_diagnostics": build_diagnostics,
        "notes": [
            "This inspector reads local files only.",
            "It does not call RunPod, compile CUDA, or run benchmarks.",
            "Age/find delivery remains paused until the speed path is stable above the 200M minimum.",
            "300M+ attempts/s is preferred before Serverless migration.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect suffix speed sweep output.")
    parser.add_argument("result_dir", help="Path to runpod_results/suffix_speed_sweep_<run-id>")
    args = parser.parse_args()
    result = inspect(Path(args.result_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
