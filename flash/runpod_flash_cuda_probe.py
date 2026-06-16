#!/usr/bin/env python3
"""
Minimal RunPod Flash CUDA environment probe.

This is a fallback path only. It does not generate TRON addresses, does not
create private keys, and does not run a vanity benchmark. Its only purpose is
to check whether a RunPod Flash GPU worker can see `nvidia-smi`, `nvcc`, and
run one tiny CUDA kernel.

Running with --confirm-runpod-side-effect may create or start a RunPod
Serverless endpoint and may spend RunPod credits. Do not run it unless the user
has explicitly confirmed that action.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any


DEFAULT_GPU_ENUM = "NVIDIA_A100_80GB_PCIe"


def _safe_endpoint_suffix(name: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", name.lower().replace("_", "-"))
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:48] or "unknown-gpu"


def build_endpoint(gpu_enum_name: str):
    from runpod_flash import Endpoint, GpuType

    try:
        gpu = getattr(GpuType, gpu_enum_name)
    except AttributeError as exc:
        available = [
            name
            for name in dir(GpuType)
            if name.startswith("NVIDIA_") and not name.startswith("__")
        ]
        raise SystemExit(
            json.dumps(
                {
                    "ok": False,
                    "error": "unknown_gpu_enum",
                    "requested": gpu_enum_name,
                    "available_examples": available[:40],
                    "notes": [
                        "RunPod Flash GPU enum names can differ from console labels.",
                        "Use an enum present in the installed runpod-flash package.",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        ) from exc

    endpoint_name = f"tron-vanity-cuda-probe-{_safe_endpoint_suffix(gpu_enum_name)}"

    @Endpoint(
        name=endpoint_name,
        gpu=gpu,
        workers=(0, 1),
        dependencies=[],
    )
    async def cuda_probe(payload: dict[str, Any]) -> dict[str, Any]:
        import os
        import pathlib
        import shutil
        import subprocess
        import tempfile
        import time

        def run_cmd(cmd: list[str], timeout: int = 20) -> dict[str, Any]:
            started = time.time()
            try:
                completed = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
                return {
                    "cmd": cmd[0],
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            except FileNotFoundError:
                return {
                    "cmd": cmd[0],
                    "returncode": None,
                    "stdout": "",
                    "stderr": "not_found",
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "cmd": cmd[0],
                    "returncode": None,
                    "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                    "stderr": "timeout",
                    "elapsed_seconds": round(time.time() - started, 3),
                }

        cuda_source = r'''
#include <cstdio>
#include <cuda_runtime.h>

__global__ void probe_kernel(int *out) {
    out[0] = 42;
}

int main() {
    int host = 0;
    int *device = nullptr;
    cudaError_t err = cudaMalloc(&device, sizeof(int));
    if (err != cudaSuccess) {
        std::fprintf(stderr, "cudaMalloc failed: %s\n", cudaGetErrorString(err));
        return 2;
    }
    probe_kernel<<<1, 1>>>(device);
    err = cudaDeviceSynchronize();
    if (err != cudaSuccess) {
        std::fprintf(stderr, "kernel failed: %s\n", cudaGetErrorString(err));
        cudaFree(device);
        return 3;
    }
    err = cudaMemcpy(&host, device, sizeof(int), cudaMemcpyDeviceToHost);
    cudaFree(device);
    if (err != cudaSuccess) {
        std::fprintf(stderr, "cudaMemcpy failed: %s\n", cudaGetErrorString(err));
        return 4;
    }
    std::printf("cuda_probe_value=%d\n", host);
    return host == 42 ? 0 : 5;
}
'''

        nvidia_smi = run_cmd(
            [
                "nvidia-smi",
                "--query-gpu=name,compute_cap,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            timeout=15,
        )
        nvcc_version = run_cmd(["nvcc", "--version"], timeout=15)

        compile_result: dict[str, Any] | None = None
        run_result: dict[str, Any] | None = None
        nvcc_path = shutil.which("nvcc")
        if nvcc_path:
            with tempfile.TemporaryDirectory(prefix="tron_vanity_cuda_probe_") as tmp:
                src_path = pathlib.Path(tmp) / "probe.cu"
                bin_path = pathlib.Path(tmp) / "probe"
                src_path.write_text(cuda_source)
                compile_result = run_cmd(
                    [nvcc_path, "-O2", str(src_path), "-o", str(bin_path)],
                    timeout=60,
                )
                if compile_result["returncode"] == 0:
                    run_result = run_cmd([str(bin_path)], timeout=20)

        passed = (
            nvidia_smi["returncode"] == 0
            and nvcc_version["returncode"] == 0
            and compile_result is not None
            and compile_result["returncode"] == 0
            and run_result is not None
            and run_result["returncode"] == 0
        )

        return {
            "mode": payload.get("mode", "cuda_probe"),
            "passed": passed,
            "gpu_enum": gpu_enum_name,
            "nvidia_smi": nvidia_smi,
            "nvcc_version": nvcc_version,
            "compile": compile_result,
            "run": run_result,
            "notes": [
                "This probe does not generate TRON addresses.",
                "This probe does not generate, print, save, or return private_key.",
                "This probe is not a vanity benchmark and does not prove 10 second matching performance.",
            ],
        }

    return cuda_probe


async def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod Flash CUDA environment probe")
    parser.add_argument(
        "--gpu-enum",
        default=DEFAULT_GPU_ENUM,
        help="GpuType enum name from runpod_flash, for example NVIDIA_A100_80GB_PCIe",
    )
    parser.add_argument(
        "--confirm-runpod-side-effect",
        action="store_true",
        help="Required before creating/starting a RunPod Flash endpoint.",
    )
    args = parser.parse_args()

    if not args.confirm_runpod_side_effect:
        print(
            json.dumps(
                {
                    "ok": False,
                    "would_create_or_start_runpod_endpoint": True,
                    "required_confirmation_flag": "--confirm-runpod-side-effect",
                    "gpu_enum": args.gpu_enum,
                    "notes": [
                        "No RunPod action was taken.",
                        "Install runpod-flash and complete flash login before confirmed use.",
                        "Confirmed use may spend RunPod credits.",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    endpoint = build_endpoint(args.gpu_enum)
    result = await endpoint({"mode": "cuda_probe"})
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
