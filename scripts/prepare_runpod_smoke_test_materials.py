#!/usr/bin/env python3
"""Prepare local-only test age recipient and smoke payload for RunPod Serverless."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict


BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
AGE_RECIPIENT_RE = re.compile(r"^age1[023456789acdefghjklmnpqrstuvwxyz]{20,}$")
DEFAULT_OUT_DIR = Path("/tmp/tron_vanity_runpod_smoke")
DEFAULT_SUFFIX = "CDEFG"
DEFAULT_DURATION_SECONDS = 15
DEFAULT_MAX_ATTEMPTS = 10_000_000_000
DEFAULT_GPU_GRID = "128,128"


def validate_suffix(suffix: str) -> str:
    if len(suffix) != 5 or any(ch not in BASE58 for ch in suffix):
        raise SystemExit("suffix must be exactly 5 Base58 characters")
    return suffix


def parse_recipient(output: str) -> str:
    match = re.search(r"age1[023456789acdefghjklmnpqrstuvwxyz]+", output)
    if not match:
        raise RuntimeError("age-keygen did not print a recipient")
    return match.group(0)


def validate_age_recipient(recipient: str) -> str:
    if not AGE_RECIPIENT_RE.match(recipient):
        raise SystemExit("age recipient must start with age1 and use age recipient characters")
    return recipient


def run_age_keygen(age_keygen_binary: str, identity_path: Path) -> str:
    if identity_path.exists():
        raise FileExistsError(f"refusing to overwrite existing identity file: {identity_path}")
    proc = subprocess.run(
        [age_keygen_binary, "-o", str(identity_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"age-keygen failed with rc={proc.returncode}: {proc.stderr.strip()}")
    os.chmod(identity_path, stat.S_IRUSR | stat.S_IWUSR)
    return parse_recipient(proc.stdout + "\n" + proc.stderr)


def build_payload(args: argparse.Namespace, recipient: str) -> Dict[str, Any]:
    return {
        "input": {
            "mode": "find",
            "suffix": args.suffix,
            "age_recipient": recipient,
            "duration_seconds": args.duration_seconds,
            "max_attempts": args.max_attempts,
            "gpu_grid": args.gpu_grid,
        },
        "policy": {
            "executionTimeout": args.execution_timeout_ms,
            "ttl": args.ttl_ms,
        },
    }


def write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create local test age materials and a RunPod Serverless smoke payload."
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX)
    parser.add_argument("--duration-seconds", type=int, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--gpu-grid", default=DEFAULT_GPU_GRID)
    parser.add_argument("--execution-timeout-ms", type=int, default=300_000)
    parser.add_argument("--ttl-ms", type=int, default=900_000)
    parser.add_argument("--endpoint-id", default="<endpoint-id>")
    parser.add_argument("--age-recipient", default="", help="existing test age recipient; skips age-keygen")
    parser.add_argument("--age-keygen-binary", default="age-keygen")
    args = parser.parse_args()

    args.suffix = validate_suffix(args.suffix)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not str(out_dir).startswith("/tmp/"):
        raise SystemExit("out-dir must be under /tmp so test identity material is not kept in the repo")

    identity_path = out_dir / "test_age_identity.txt"
    if args.age_recipient:
        recipient = validate_age_recipient(args.age_recipient)
        identity_written = False
    else:
        recipient = run_age_keygen(args.age_keygen_binary, identity_path)
        identity_written = True
    payload = build_payload(args, recipient)

    payload_path = out_dir / "smoke_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dry_run_path = out_dir / "dry_run_command.sh"
    write_executable(
        dry_run_path,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "scripts/runpod_serverless_find_e2e.py \\\n"
        "  --dry-run \\\n"
        f"  --endpoint-id {args.endpoint_id!r} \\\n"
        f"  --age-recipient {recipient!r} \\\n"
        f"  --suffix {args.suffix!r} \\\n"
        "  --samples 11 \\\n"
        "  --cold-count 1\n",
    )

    smoke_path = out_dir / "paid_smoke_command.sh"
    write_executable(
        smoke_path,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1 \\\n"
        "  scripts/runpod_serverless_find_e2e.py \\\n"
        f"  --endpoint-id {args.endpoint_id!r} \\\n"
        f"  --age-recipient {recipient!r} \\\n"
        f"  --suffix {args.suffix!r} \\\n"
        "  --samples 1 \\\n"
        "  --cold-count 0 \\\n"
        "  --allow-short-smoke \\\n"
        "  --out-dir serverless_find_smoke\n",
    )

    result = {
        "mode": "prepare_runpod_smoke_test_materials",
        "passed": True,
        "out_dir": str(out_dir),
        "recipient": recipient,
        "identity_path": str(identity_path) if identity_written else None,
        "identity_written": identity_written,
        "payload_path": str(payload_path),
        "dry_run_command_path": str(dry_run_path),
        "paid_smoke_command_path": str(smoke_path),
        "notes": [
            "This script does not call RunPod.",
            "The recipient is public test material; the identity file is local-only and must not be committed.",
            "If --age-recipient is supplied, no identity file is written and decrypt verification needs the matching identity from elsewhere.",
            "Delete the out_dir after the smoke/E2E inspection is done.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
