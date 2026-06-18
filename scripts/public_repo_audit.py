#!/usr/bin/env python3
"""Audit this repository before making it visible to RunPod/GitHub.

The audit is intentionally conservative around credential-like files, but it
allows the public TEST_ONLY vector file to contain `private_key_hex` because
those deterministic vectors are part of the correctness gate and are documented
as unsafe for funds.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NAME_PATTERNS = [
    re.compile(r"(^|/)\.env($|\.)", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(^|/).*secret.*", re.IGNORECASE),
    re.compile(r"(^|/).*token.*", re.IGNORECASE),
    re.compile(r"(^|/)runpod_.*_(response|inspect)\.json$", re.IGNORECASE),
]

FORBIDDEN_TRACKED_PATHS = {
    "tests/phase0_filter_validation_report.json",
}

ALLOWED_PRIVATE_KEY_PATHS = {
    "tests/phase0_test_vectors.json",
}

ALLOWED_AUDIT_MARKER_PATHS = {
    "scripts/public_repo_audit.py",
    "scripts/runpod_serverless_find_e2e.py",
    "scripts/runpod_serverless_readiness_check.py",
    "docs/RUNPOD_SERVERLESS_FIND_E2E_NEXT.md",
    "docs/RUNPOD_RESPONSE_INTAKE.md",
}

REQUIRED_PATHS = [
    "Dockerfile",
    "app.py",
    "requirements.txt",
    "src/tron_gpu_core.cu",
    "src/secp256k1_device.cuh",
    "src/tron_core_device.cuh",
    "tests/phase0_test_vectors.json",
    "RUNPOD_VALIDATE_PAYLOAD.json",
    "RUNPOD_BENCHMARK_SMOKE_PAYLOAD.json",
    "RUNPOD_A100_BENCHMARK_10S_PAYLOAD.json",
    "RUNPOD_RTX5090_BENCHMARK_10S_PAYLOAD.json",
    "examples/vanitysearch_bounded_benchmark_sample.txt",
    "examples/runpod_find_success_sample.json",
    "docs/RUNPOD_ACTION_NOW.md",
    "docs/RUNPOD_BENCHMARK_GATE.md",
    "docs/RUNPOD_GITHUB_UPLOAD_CHECKLIST.md",
    "docs/RUNPOD_GPU_POD_NEXT_CHECK.md",
    "docs/RUNPOD_GPU_POD_RESULT_TEMPLATE.md",
    "docs/RUNPOD_SUFFIX_ONLY_GPU_POD_NEXT.md",
    "docs/RUNPOD_VANITYSEARCH_GPU_ADDRESS_LAYER_CHECK.md",
    "scripts/inspect_suffix_speed_sweep.py",
    "scripts/inspect_runpod_sequence_result.py",
    "scripts/inspect_serverless_find_e2e.py",
    "patches/vanitysearch_tron_gpu_suffix_only_20260618.patch",
    "scripts/inspect_vanitysearch_benchmark.py",
    "scripts/print_runpod_suffix_only_commands.sh",
    "scripts/runpod_gpu_pod_suffix_speed_sweep.sh",
    "scripts/runpod_gpu_pod_suffix_speed_test.sh",
    "scripts/runpod_gpu_pod_suffix_compare_commits.sh",
    "scripts/runpod_gpu_pod_sequence.sh",
    "scripts/runpod_serverless_find_e2e.py",
    "scripts/runpod_serverless_readiness_check.py",
    "scripts/verify_age_encrypted_find_response.py",
    "scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh",
    "tests/verify_find_response_contract.py",
]


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def tracked_files() -> list[str]:
    return [line for line in run_git(["ls-files"]).splitlines() if line]


def is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\0" in chunk


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []
    files = tracked_files()
    file_set = set(files)

    for required in REQUIRED_PATHS:
        if required not in file_set:
            failures.append(f"missing required tracked path: {required}")

    for rel in files:
        if rel in FORBIDDEN_TRACKED_PATHS:
            failures.append(f"forbidden generated tracked path: {rel}")
        for pattern in FORBIDDEN_NAME_PATTERNS:
            if pattern.search(rel):
                failures.append(f"sensitive-looking tracked filename: {rel}")

        path = ROOT / rel
        if is_binary(path):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue

        lowered = text.lower()
        if rel not in ALLOWED_AUDIT_MARKER_PATHS and (
            "runpod_api_key" in lowered or "api_key=" in lowered
        ):
            failures.append(f"possible API key material marker in: {rel}")
        if "private_key" in lowered and rel not in ALLOWED_PRIVATE_KEY_PATHS:
            if "private_key" in rel.lower():
                failures.append(f"private key marker in path: {rel}")
            elif "private_key" in lowered and "do not output plaintext `private_key`" not in lowered:
                notes.append(f"private_key text mention reviewed in: {rel}")

    status = run_git(["status", "--short"])
    if status.strip():
        failures.append("git worktree is not clean")

    phase0 = ROOT / "tests/phase0_test_vectors.json"
    try:
        data = json.loads(phase0.read_text())
        serialized = json.dumps(data).lower()
        if "test_only" not in serialized:
            failures.append("phase0 vectors do not clearly contain TEST_ONLY marker")
    except Exception as exc:  # noqa: BLE001 - audit should report parse issue plainly.
        failures.append(f"failed to parse phase0 vectors: {exc}")

    result = {
        "mode": "public_repo_audit",
        "root": str(ROOT),
        "tracked_files": len(files),
        "passed": not failures,
        "failures": failures,
        "notes": notes[:50],
        "safety_notes": [
            "No files are uploaded by this audit.",
            "No RunPod API calls are made by this audit.",
            "tests/phase0_test_vectors.json contains public TEST_ONLY private_key_hex values only.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
