#!/usr/bin/env python3
"""Run controlled RunPod Serverless find E2E samples and save responses.

This script intentionally refuses to run unless explicitly enabled. It uses the
async /run path and polls /status/<job_id>; it does not use /runsync.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


DEFAULT_API_BASE = "https://api.runpod.ai/v2"
DEFAULT_OUT_DIR = "serverless_find_e2e"


def utc_ms() -> int:
    return int(time.time() * 1000)


def require_enabled(dry_run: bool) -> None:
    if dry_run:
        return
    if os.environ.get("ALLOW_RUNPOD_SERVERLESS_FIND_E2E") != "1":
        raise SystemExit(
            "refusing_to_run_without_ALLOW_RUNPOD_SERVERLESS_FIND_E2E=1\n"
            "This may spend RunPod credits. Use only with a test age recipient and no customer data."
        )


def env_or_arg(value: str | None, env_name: str, label: str) -> str:
    chosen = value or os.environ.get(env_name, "")
    if not chosen:
        raise SystemExit(f"missing {label}; pass the argument or set {env_name}")
    return chosen


def validate_suffix(suffix: str) -> str:
    alphabet = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    if len(suffix) != 5 or any(ch not in alphabet for ch in suffix):
        raise SystemExit("suffix must be exactly 5 Base58 characters")
    return suffix


def validate_age_recipient(recipient: str) -> str:
    if not recipient.startswith("age1") or len(recipient) < 20:
        raise SystemExit("age recipient must be a test age recipient beginning with age1")
    return recipient


def request_json(method: str, url: str, api_key: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - user-gated HTTPS API call.
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RunPod HTTP {exc.code}: {body[:500]}") from exc
    if not raw.strip():
        return {}
    data_obj = json.loads(raw)
    if not isinstance(data_obj, dict):
        raise RuntimeError("RunPod response was not a JSON object")
    return data_obj


def build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "input": {
            "mode": "find",
            "suffix": args.suffix,
            "age_recipient": args.age_recipient,
            "duration_seconds": args.duration_seconds,
            "max_attempts": args.max_attempts,
            "gpu_grid": args.gpu_grid,
        },
        "policy": {
            "executionTimeout": args.execution_timeout_ms,
            "ttl": args.ttl_ms,
        },
    }


def job_id_from_run_response(response: Dict[str, Any]) -> str | None:
    for key in ("id", "jobId", "job_id"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def is_complete(status: Dict[str, Any]) -> bool:
    value = str(status.get("status", "")).upper()
    return value in {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "TIMEOUT"}


def run_one(args: argparse.Namespace, api_key: str, index: int) -> Dict[str, Any]:
    payload = build_payload(args)
    run_url = f"{args.api_base.rstrip('/')}/{args.endpoint_id}/run"
    started = time.perf_counter()
    started_ms = utc_ms()
    run_response = request_json("POST", run_url, api_key, payload)
    job_id = job_id_from_run_response(run_response)
    if not job_id:
        # Some APIs can return a completed object directly; still save it with timing.
        run_response["request_latency_seconds"] = time.perf_counter() - started
        run_response["client_started_ms"] = started_ms
        run_response["client_finished_ms"] = utc_ms()
        run_response["sample_index"] = index
        return run_response

    status_url = f"{args.api_base.rstrip('/')}/{args.endpoint_id}/status/{job_id}"
    deadline = time.perf_counter() + args.max_wait_seconds
    status_response: Dict[str, Any] = run_response
    while time.perf_counter() < deadline:
        time.sleep(args.poll_interval_seconds)
        status_response = request_json("GET", status_url, api_key)
        if is_complete(status_response):
            break
    else:
        status_response = {
            "id": job_id,
            "status": "CLIENT_POLL_TIMEOUT",
            "output": {},
        }

    status_response["request_latency_seconds"] = time.perf_counter() - started
    status_response["client_started_ms"] = started_ms
    status_response["client_finished_ms"] = utc_ms()
    status_response["sample_index"] = index
    return status_response


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled RunPod Serverless find E2E samples.")
    parser.add_argument("--endpoint-id", default=None, help="RunPod endpoint id; or RUNPOD_ENDPOINT_ID")
    parser.add_argument("--api-key-env", default="RUNPOD_API_KEY", help="Environment variable containing the API key")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--suffix", default="CDEFG", help="Five-character Base58 suffix for test only")
    parser.add_argument("--age-recipient", default=os.environ.get("TEST_AGE_RECIPIENT", ""))
    parser.add_argument("--samples", type=int, default=11)
    parser.add_argument("--cold-count", type=int, default=1)
    parser.add_argument("--duration-seconds", type=int, default=15)
    parser.add_argument("--max-attempts", type=int, default=10_000_000_000)
    parser.add_argument("--gpu-grid", default="128,128")
    parser.add_argument("--execution-timeout-ms", type=int, default=300_000)
    parser.add_argument("--ttl-ms", type=int, default=900_000)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-wait-seconds", type=float, default=180.0)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print payload without calling RunPod")
    parser.add_argument("--allow-short-smoke", action="store_true", help="Allow fewer than 10 warm samples for a first smoke test")
    args = parser.parse_args()

    require_enabled(args.dry_run)
    args.endpoint_id = env_or_arg(args.endpoint_id, "RUNPOD_ENDPOINT_ID", "RunPod endpoint id")
    api_key = "" if args.dry_run else env_or_arg(None, args.api_key_env, "RunPod API key")
    args.suffix = validate_suffix(args.suffix)
    args.age_recipient = validate_age_recipient(args.age_recipient)
    if args.samples < 1:
        raise SystemExit("samples must be at least 1")
    if args.cold_count < 0 or args.cold_count > args.samples:
        raise SystemExit("cold-count must be between 0 and samples")
    if args.samples < args.cold_count + 10 and not args.allow_short_smoke:
        raise SystemExit("samples must include cold-count plus at least 10 warm samples")

    if args.dry_run:
        print(json.dumps({
            "mode": "runpod_serverless_find_e2e_dry_run",
            "would_call_runpod": False,
            "endpoint_id": args.endpoint_id,
            "api_base": args.api_base,
            "samples": args.samples,
            "cold_count": args.cold_count,
            "allow_short_smoke": args.allow_short_smoke,
            "out_dir": args.out_dir,
            "payload": build_payload(args),
            "notes": [
                "Dry run does not read the RunPod API key.",
                "Dry run does not call RunPod.",
                "Dry run does not write response files.",
                "Short smoke mode is not final P90 evidence.",
            ],
        }, indent=2, sort_keys=True))
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "mode": "runpod_serverless_find_e2e_manifest",
        "endpoint_id": args.endpoint_id,
        "suffix": args.suffix,
        "samples": args.samples,
        "cold_count": args.cold_count,
        "allow_short_smoke": args.allow_short_smoke,
        "duration_seconds": args.duration_seconds,
        "gpu_grid": args.gpu_grid,
        "notes": [
            "API key is read only from the selected environment variable and is not written to disk.",
            "Use only test age recipients and no customer data.",
            "Inspect outputs with scripts/inspect_serverless_find_e2e.py.",
            "Short smoke mode is not final P90 evidence.",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)

    for index in range(args.samples):
        response = run_one(args, api_key, index)
        write_json(out_dir / f"find_{index:02d}.json", response)
        status = response.get("status")
        latency = response.get("request_latency_seconds")
        print(json.dumps({
            "sample_index": index,
            "status": status,
            "request_latency_seconds": latency,
            "path": str(out_dir / f"find_{index:02d}.json"),
        }, sort_keys=True))
        sys.stdout.flush()

    inspect_command = (
        f"scripts/inspect_serverless_find_e2e.py {out_dir} --cold-count {args.cold_count}"
        if args.samples >= args.cold_count + 10
        else f"scripts/inspect_runpod_result.py {out_dir / 'find_00.json'} --mode find"
    )
    print(json.dumps({
        "mode": "runpod_serverless_find_e2e_complete",
        "out_dir": str(out_dir),
        "inspect_command": inspect_command,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
