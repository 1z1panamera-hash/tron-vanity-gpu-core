#!/usr/bin/env python3
"""Create a short-lived RunPod GPU Pod, run suffix autotune, then clean up.

This script is intentionally gated. Dry-run mode does not read the RunPod API
key, does not call RunPod, and does not create any resources.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "https://rest.runpod.io/v1"
DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
DEFAULT_REPO = "https://github.com/1z1panamera-hash/tron-vanity-gpu-core.git"
DEFAULT_OUT_ROOT = Path("runpod_results/fixed_pod_autotune")
DEFAULT_GPU_PRIORITY = [
    "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
    "NVIDIA H200",
    "NVIDIA H200 NVL",
    "NVIDIA H100 80GB HBM3",
    "NVIDIA H100 NVL",
    "NVIDIA H100 PCIe",
    "NVIDIA A100-SXM4-80GB",
    "NVIDIA A100 80GB PCIe",
    "NVIDIA L40S",
    "NVIDIA A40",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 3090",
]


def utc_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def require_enabled(dry_run: bool) -> None:
    if dry_run:
        return
    if os.environ.get("ALLOW_RUNPOD_FIXED_POD_AUTOTUNE") != "1":
        raise SystemExit(
            "refusing_to_run_without_ALLOW_RUNPOD_FIXED_POD_AUTOTUNE=1\n"
            "This creates a paid RunPod GPU Pod. Use only for controlled speed tests."
        )


def get_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise SystemExit(f"missing RunPod API key env var: {env_name}")
    return value


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    *,
    expect_empty: bool = False,
) -> Any:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - user-gated HTTPS API call.
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RunPod HTTP {exc.code}: {body[:800]}") from exc
    if expect_empty or not raw.strip():
        return {}
    return json.loads(raw)


def shell(command: list[str], *, input_text: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def parse_gpu_priority(value: str) -> list[str]:
    if not value.strip():
        return DEFAULT_GPU_PRIORITY
    return [item.strip() for item in value.split(",") if item.strip()]


def build_create_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "allowedCudaVersions": args.allowed_cuda_versions,
        "cloudType": args.cloud_type,
        "computeType": "GPU",
        "containerDiskInGb": args.container_disk_gb,
        "dataCenterPriority": "availability",
        "gpuCount": 1,
        "gpuTypeIds": args.gpu_priority,
        "gpuTypePriority": args.gpu_type_priority,
        "imageName": args.image_name,
        "interruptible": args.interruptible,
        "locked": False,
        "minRAMPerGPU": args.min_ram_per_gpu,
        "minVCPUPerGPU": args.min_vcpu_per_gpu,
        "name": args.pod_name,
        "ports": ["22/tcp"],
        "supportPublicIp": True,
        "volumeInGb": args.volume_gb,
        "volumeMountPath": "/workspace",
    }
    if args.template_id:
        payload["templateId"] = args.template_id
    return payload


def create_pod(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    return request_json("POST", f"{args.api_base.rstrip('/')}/pods", api_key, build_create_payload(args))


def get_pod(args: argparse.Namespace, api_key: str, pod_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "id": pod_id,
        "includeMachine": "true",
        "includeNetworkVolume": "true",
    })
    data = request_json("GET", f"{args.api_base.rstrip('/')}/pods?{query}", api_key)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id") == pod_id:
                return item
    raise RuntimeError(f"pod not found in list response: {pod_id}")


def wait_for_ssh(args: argparse.Namespace, api_key: str, pod_id: str) -> dict[str, Any]:
    deadline = time.time() + args.wait_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = get_pod(args, api_key, pod_id)
        public_ip = last.get("publicIp")
        port_mappings = last.get("portMappings") or {}
        ssh_port = port_mappings.get("22") or port_mappings.get(22)
        if public_ip and ssh_port:
            return last
        time.sleep(args.poll_seconds)
    raise TimeoutError(f"pod did not expose SSH before timeout; last_status={last.get('desiredStatus')}")


def ssh_target(pod: dict[str, Any]) -> tuple[str, int]:
    public_ip = pod.get("publicIp")
    port_mappings = pod.get("portMappings") or {}
    ssh_port = port_mappings.get("22") or port_mappings.get(22)
    if not public_ip or not ssh_port:
        raise RuntimeError("pod has no public SSH mapping")
    return str(public_ip), int(ssh_port)


def wait_for_ssh_login(args: argparse.Namespace, pod: dict[str, Any]) -> None:
    host, port = ssh_target(pod)
    deadline = time.time() + args.ssh_wait_seconds
    command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-p",
        str(port),
        f"root@{host}",
        "echo ssh_ready",
    ]
    while time.time() < deadline:
        proc = shell(command, timeout=20)
        if proc.returncode == 0 and "ssh_ready" in proc.stdout:
            return
        time.sleep(args.poll_seconds)
    raise TimeoutError("SSH login did not become ready")


def remote_autotune_script(args: argparse.Namespace) -> str:
    repo = shlex.quote(args.repo_url)
    commit = shlex.quote(args.repo_commit)
    seconds = shlex.quote(str(args.benchmark_seconds))
    return f"""#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
mkdir -p /workspace
cd /workspace
if [ ! -d tron-vanity-gpu-core/.git ]; then
  git clone {repo} tron-vanity-gpu-core
fi
cd tron-vanity-gpu-core
git fetch --all --quiet
git checkout --quiet {commit}
git rev-parse HEAD
if ! command -v g++ >/dev/null 2>&1 || ! command -v make >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends git g++ make ca-certificates
fi
ALLOW_RUNPOD_SUFFIX_AUTOTUNE=1 BENCHMARK_SECONDS={seconds} scripts/runpod_gpu_pod_suffix_autotune.sh
latest_dir="$(ls -dt runpod_results/suffix_autotune_* | head -1)"
tar -czf /workspace/tron_suffix_autotune_result.tgz "$latest_dir"
"""


def run_remote_autotune(args: argparse.Namespace, pod: dict[str, Any], out_dir: Path) -> None:
    host, port = ssh_target(pod)
    target = f"root@{host}"
    ssh_base = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        str(port),
        target,
    ]
    script = remote_autotune_script(args)
    proc = shell([*ssh_base, "bash -s"], input_text=script, timeout=args.remote_timeout_seconds)
    (out_dir / "remote_stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "remote_stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"remote autotune failed rc={proc.returncode}; see {out_dir}")
    scp = shell([
        "scp",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-P",
        str(port),
        f"{target}:/workspace/tron_suffix_autotune_result.tgz",
        str(out_dir / "tron_suffix_autotune_result.tgz"),
    ], timeout=300)
    (out_dir / "scp_stdout.txt").write_text(scp.stdout, encoding="utf-8")
    (out_dir / "scp_stderr.txt").write_text(scp.stderr, encoding="utf-8")
    if scp.returncode != 0:
        raise RuntimeError(f"scp result failed rc={scp.returncode}; see {out_dir}")
    unpack = shell(["tar", "-xzf", str(out_dir / "tron_suffix_autotune_result.tgz"), "-C", str(out_dir)], timeout=120)
    if unpack.returncode != 0:
        raise RuntimeError(f"unpack result failed: {unpack.stderr[:500]}")


def stop_pod(args: argparse.Namespace, api_key: str, pod_id: str) -> None:
    request_json("POST", f"{args.api_base.rstrip('/')}/pods/{pod_id}/stop", api_key, expect_empty=True)


def delete_pod(args: argparse.Namespace, api_key: str, pod_id: str) -> None:
    request_json("DELETE", f"{args.api_base.rstrip('/')}/pods/{pod_id}", api_key, expect_empty=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a one-shot fixed RunPod GPU Pod suffix autotune.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without reading API key or creating resources")
    parser.add_argument("--api-key-env", default="RUNPOD_API_KEY")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--repo-url", default=DEFAULT_REPO)
    parser.add_argument("--repo-commit", default="HEAD")
    parser.add_argument("--pod-name", default=f"tron-suffix-autotune-{utc_run_id().lower()}")
    parser.add_argument("--gpu-priority", default="", help="Comma-separated RunPod gpuTypeIds; default is high-end-first")
    parser.add_argument("--gpu-type-priority", choices=["availability", "custom"], default="custom")
    parser.add_argument("--cloud-type", choices=["SECURE", "COMMUNITY"], default="SECURE")
    parser.add_argument("--image-name", default=DEFAULT_IMAGE)
    parser.add_argument("--template-id", default="", help="Optional RunPod template id if image-only SSH is not enough")
    parser.add_argument("--allowed-cuda-versions", nargs="*", default=["12.8", "12.7", "12.6", "12.5", "12.4"])
    parser.add_argument("--container-disk-gb", type=int, default=20)
    parser.add_argument("--volume-gb", type=int, default=20)
    parser.add_argument("--min-ram-per-gpu", type=int, default=16)
    parser.add_argument("--min-vcpu-per-gpu", type=int, default=4)
    parser.add_argument("--interruptible", action="store_true", help="Use spot/interruptible Pod; off by default")
    parser.add_argument("--benchmark-seconds", type=int, default=3)
    parser.add_argument("--wait-seconds", type=int, default=900)
    parser.add_argument("--ssh-wait-seconds", type=int, default=420)
    parser.add_argument("--remote-timeout-seconds", type=int, default=2400)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--keep-pod", action="store_true", help="Do not stop/delete the Pod after the run")
    args = parser.parse_args()

    require_enabled(args.dry_run)
    if args.benchmark_seconds < 3 or args.benchmark_seconds > 15:
        raise SystemExit("benchmark-seconds must be between 3 and 15")
    args.gpu_priority = parse_gpu_priority(args.gpu_priority)
    if args.repo_commit == "HEAD":
        proc = shell(["git", "rev-parse", "HEAD"], timeout=20)
        if proc.returncode == 0:
            args.repo_commit = proc.stdout.strip()

    out_dir = Path(args.out_root) / utc_run_id()
    plan = {
        "mode": "runpod_fixed_pod_autotune_plan",
        "would_call_runpod": not args.dry_run,
        "api_base": args.api_base,
        "pod_name": args.pod_name,
        "repo_url": args.repo_url,
        "repo_commit": args.repo_commit,
        "gpu_priority": args.gpu_priority,
        "gpu_type_priority": args.gpu_type_priority,
        "cloud_type": args.cloud_type,
        "image_name": args.image_name,
        "template_id": args.template_id or None,
        "container_disk_gb": args.container_disk_gb,
        "volume_gb": args.volume_gb,
        "benchmark_seconds": args.benchmark_seconds,
        "out_dir": str(out_dir),
        "cleanup": "keep-pod" if args.keep_pod else "stop-and-delete",
        "notes": [
            "Dry run does not read RUNPOD_API_KEY.",
            "Execution mode creates a paid Pod and removes it unless --keep-pod is set.",
            "The script never prints or writes the RunPod API key.",
        ],
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    api_key = get_api_key(args.api_key_env)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "plan.json", plan)
    pod_id = ""
    cleanup_errors: list[str] = []
    try:
        created = create_pod(args, api_key)
        write_json(out_dir / "pod_created.json", created if isinstance(created, dict) else {"response": created})
        pod_id = str(created.get("id") or "")
        if not pod_id:
            raise RuntimeError("RunPod create response did not include pod id")
        pod = wait_for_ssh(args, api_key, pod_id)
        write_json(out_dir / "pod_ready.json", pod)
        wait_for_ssh_login(args, pod)
        run_remote_autotune(args, pod, out_dir)
        final_pod = get_pod(args, api_key, pod_id)
        write_json(out_dir / "pod_final.json", final_pod)
        result = {
            "mode": "runpod_fixed_pod_autotune_result",
            "passed": True,
            "pod_id": pod_id,
            "out_dir": str(out_dir),
            "notes": [
                "Result archive was copied locally.",
                "Inspect speed_sweep_inspect.json under the extracted result directory.",
            ],
        }
        write_json(out_dir / "result.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        if pod_id and not args.keep_pod:
            try:
                stop_pod(args, api_key, pod_id)
            except Exception as exc:  # noqa: BLE001 - cleanup must continue.
                cleanup_errors.append(f"stop failed: {exc}")
            try:
                delete_pod(args, api_key, pod_id)
            except Exception as exc:  # noqa: BLE001 - cleanup must be reported.
                cleanup_errors.append(f"delete failed: {exc}")
            if cleanup_errors:
                write_json(out_dir / "cleanup_errors.json", {"errors": cleanup_errors})


if __name__ == "__main__":
    raise SystemExit(main())
