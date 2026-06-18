#!/usr/bin/env python3
"""Local readiness check before creating/updating the RunPod Serverless endpoint."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "patches" / "vanitysearch_tron_gpu_suffix_only_20260618.patch"
EXPECTED_PATCH_SHA = "6c7af24b0d4abd909869acb2fdbf537758eee701b239740e5ea9d1b2311390ca"
BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
REQUIRED_FILES = [
    "Dockerfile",
    "app.py",
    "requirements.txt",
    "patches/vanitysearch_tron_gpu_suffix_only_20260618.patch",
    "scripts/build_vanitysearch_tron_worker.sh",
    "scripts/runpod_serverless_find_e2e.py",
    "scripts/inspect_runpod_result.py",
    "scripts/inspect_serverless_find_e2e.py",
    "scripts/verify_age_encrypted_find_response.py",
    "RUNPOD_FIND_SAMPLE_PAYLOAD.json",
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def git(args: List[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def add(condition: bool, failures: List[str], message: str) -> None:
    if not condition:
        failures.append(message)


def load_payload(rel: str) -> Dict[str, Any]:
    data = json.loads(read(rel))
    if not isinstance(data, dict):
        raise ValueError(f"{rel} must be a JSON object")
    return data


def main() -> int:
    failures: List[str] = []
    warnings: List[str] = []

    for rel in REQUIRED_FILES:
        add((ROOT / rel).exists(), failures, f"missing required file: {rel}")

    status = git(["status", "--short"])
    add(status == "", failures, "git worktree is not clean")
    commit = git(["rev-parse", "HEAD"])

    if PATCH_PATH.exists():
        actual_patch_sha = hashlib.sha256(PATCH_PATH.read_bytes()).hexdigest()
        add(actual_patch_sha == EXPECTED_PATCH_SHA, failures, "VanitySearch patch sha mismatch")
    else:
        actual_patch_sha = None

    dockerfile = read("Dockerfile")
    add("nvidia/cuda:12.8.1-devel-ubuntu22.04" in dockerfile, failures, "Dockerfile does not use the expected CUDA devel base image")
    add(" age " in dockerfile or "\nage \\" in dockerfile, failures, "Dockerfile does not install age")
    add("COPY patches /app/patches" in dockerfile, failures, "Dockerfile does not copy patches")
    add("COPY scripts/build_vanitysearch_tron_worker.sh" in dockerfile, failures, "Dockerfile does not copy build helper")
    add("ALLOW_BUILD_VANITYSEARCH_TRON_WORKER=1" in dockerfile, failures, "Dockerfile does not build patched VanitySearch worker")
    add("INSTALL_PATH=/app/build/vanitysearch_tron_worker" in dockerfile, failures, "Dockerfile does not install VanitySearch worker at expected path")
    add('CMD ["python3", "-u", "/app/app.py"]' in dockerfile, failures, "Dockerfile CMD is not the RunPod handler entrypoint")

    build_script = read("scripts/build_vanitysearch_tron_worker.sh")
    add(EXPECTED_PATCH_SHA in build_script, failures, "build helper does not enforce expected patch sha")
    add("scripts/runpod_verify_tron_gpu_address_layer.sh" in build_script, failures, "build helper does not run TRON GPU address-layer vector check")
    add("STEP_SIZE=\"${STEP_SIZE:-4096}\"" in build_script, failures, "build helper does not default STEP_SIZE to 4096")

    app = read("app.py")
    add("DEFAULT_PREFIX_LEN = 0" in app, failures, "app.py default prefix length is not suffix-only")
    add("DEFAULT_SUFFIX_LEN = 5" in app, failures, "app.py default suffix length is not 5")
    add("prefix_after_t is no longer accepted" in app, failures, "app.py does not reject prefix_after_t")
    add("ALLOW_GPU_FIND" in app, failures, "app.py find mode is not gated")
    add("TRON_JSON_HIT_OUTPUT" in app, failures, "app.py does not request internal JSON hit output")
    add("encrypt_private_key_with_age" in app, failures, "app.py does not call age encryption path")
    add("VANITYSEARCH_BINARY_PATH = ROOT / \"build\" / \"vanitysearch_tron_worker\"" in app, failures, "app.py does not point to the built VanitySearch worker")

    payload = load_payload("RUNPOD_FIND_SAMPLE_PAYLOAD.json")
    input_payload = payload.get("input", {})
    suffix = input_payload.get("suffix")
    add(input_payload.get("mode") == "find", failures, "sample find payload mode is not find")
    add(isinstance(suffix, str) and len(suffix) == 5 and all(ch in BASE58 for ch in suffix), failures, "sample find payload suffix is not 5 Base58 characters")
    add("prefix_len" not in input_payload and "suffix_len" not in input_payload and "prefix_after_t" not in input_payload, failures, "sample find payload contains old prefix/suffix fields")
    add(isinstance(input_payload.get("age_recipient"), str) and input_payload.get("age_recipient", "").startswith("age1"), failures, "sample find payload does not contain a test age recipient placeholder")
    add(input_payload.get("duration_seconds") == 15, failures, "sample find payload duration_seconds should be 15 for smoke")
    add(input_payload.get("max_attempts") == 10_000_000_000, failures, "sample find payload max_attempts should allow a real suffix-only hit")

    runner = read("scripts/runpod_serverless_find_e2e.py")
    add("ALLOW_RUNPOD_SERVERLESS_FIND_E2E" in runner, failures, "Serverless E2E runner is not gated")
    add("/run" in runner and "/status/" in runner, failures, "Serverless E2E runner does not use async run/status flow")
    add("--allow-short-smoke" in runner, failures, "Serverless E2E runner lacks short smoke mode")
    add("samples must include cold-count plus at least 10 warm samples" in runner, failures, "Serverless E2E runner does not enforce warm sample count")

    batch_inspector = read("scripts/inspect_serverless_find_e2e.py")
    add("--age-identity" in batch_inspector, failures, "batch E2E inspector cannot verify age envelopes")
    add("TARGET_AVG_SECONDS = 5.0" in batch_inspector, failures, "batch E2E inspector average target is not 5s")
    add("TARGET_P90_SECONDS = 8.0" in batch_inspector, failures, "batch E2E inspector P90 target is not 8s")

    if "RUNPOD_API_KEY" in "\n".join(read(rel) for rel in REQUIRED_FILES if (ROOT / rel).is_file()):
        warnings.append("RunPod API key env name is mentioned only as an environment variable; do not write actual keys to files.")

    result = {
        "mode": "runpod_serverless_readiness_check",
        "passed": not failures,
        "commit": commit,
        "patch_sha256": actual_patch_sha,
        "find_suffix": suffix,
        "failures": failures,
        "warnings": warnings,
        "next_steps": [
            "Use RunPod to build the image from this GitHub commit.",
            "Run one short Serverless find smoke with a generated test age recipient.",
            "Inspect the smoke response locally before running cold/warm E2E.",
            "Run 1 cold + 10 warm samples and inspect latency plus age envelopes.",
        ],
        "notes": [
            "This check does not call RunPod.",
            "This check does not read any API key.",
            "This check does not build Docker or run a benchmark.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
