#!/usr/bin/env python3
"""Verify a RunPod find response age envelope without printing decrypted data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import inspect_runpod_result  # noqa: E402


def require_hex_payload(value: bytes) -> None:
    text = value.decode("utf-8", errors="strict").strip()
    if len(text) != 64:
        raise ValueError("decrypted payload is not 64 hex characters")
    int(text, 16)


def decrypt_age(ciphertext: str, identity: Path, age_binary: str) -> bytes:
    if not identity.exists() or not identity.is_file():
        raise FileNotFoundError(f"age identity file not found: {identity}")
    proc = subprocess.run(
        [age_binary, "-d", "-i", str(identity)],
        input=ciphertext.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"age decrypt failed with rc={proc.returncode}: {stderr}")
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify age-encrypted RunPod find response without printing decrypted key material."
    )
    parser.add_argument("path", help="RunPod find response JSON path, or '-' for stdin")
    parser.add_argument("--identity", required=True, help="local test age identity file")
    parser.add_argument("--age-binary", default="age", help="age binary path, default: age")
    args = parser.parse_args()

    data = inspect_runpod_result.load_json(args.path)
    forbidden = inspect_runpod_result.find_forbidden(data)
    result = inspect_runpod_result.unwrap_runpod(data)
    passed, failures, summary = inspect_runpod_result.inspect_find(result)
    if forbidden:
        failures.append("forbidden keys found: " + ", ".join(forbidden))
        passed = False

    decrypt_ok = False
    if passed:
        try:
            decrypted = decrypt_age(
                result["encrypted_private_key"],
                Path(args.identity),
                args.age_binary,
            )
            require_hex_payload(decrypted)
            decrypt_ok = True
        except Exception as exc:
            failures.append(str(exc))
            passed = False

    print(json.dumps({
        "verifier": "age_encrypted_find_response",
        "passed": passed,
        "find_response_contract_passed": summary.get("has_age_ciphertext") is True and not forbidden,
        "age_decrypt_passed": decrypt_ok,
        "matched_address": summary.get("matched_address"),
        "suffix": summary.get("suffix"),
        "gpu_worker_backend": summary.get("gpu_worker_backend"),
        "failures": failures,
        "notes": [
            "This verifier does not call RunPod.",
            "This verifier does not print decrypted key material.",
            "Use only a local test age identity; never store customer identity material in the repo or on 47.80.70.211.",
        ],
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
