import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import runpod
except Exception:  # pragma: no cover - local static checks may not install runpod.
    runpod = None


ROOT = Path(__file__).resolve().parent
TEST_VECTOR_PATH = ROOT / "tests" / "phase0_test_vectors.json"
GPU_BINARY_PATH = ROOT / "build" / "tron_gpu_worker"
GPU_SOURCE_PATH = ROOT / "src" / "tron_gpu_core.cu"
DEFAULT_PREFIX_LEN = 2
DEFAULT_SUFFIX_LEN = 5
MAX_BENCHMARK_SECONDS = 10
MAX_BENCHMARK_ATTEMPTS = 10_000_000_000
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
DEFAULT_CUDA_ARCH_FALLBACKS = ["native", "sm_120", "sm_80"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_phase0_vectors() -> List[Dict[str, Any]]:
    data = json.loads(TEST_VECTOR_PATH.read_text(encoding="utf-8"))
    vectors = data.get("vectors", [])
    if not isinstance(vectors, list) or not vectors:
        raise ValueError("phase0 test vectors are missing")
    return vectors


def validate_vector_file() -> Dict[str, Any]:
    required = {
        "label",
        "private_key_hex",
        "public_key_uncompressed_hex",
        "keccak256_pubkey_without_04",
        "tron_hex_address",
        "payload25_hex",
        "tron_base58_address",
        "prefix2",
        "suffix5",
        "source",
        "warning",
    }
    vectors = load_phase0_vectors()
    failures = []
    for vector in vectors:
        missing = sorted(required - set(vector))
        if missing:
            failures.append({"label": vector.get("label"), "missing": missing})
        if vector.get("source") != "TEST_ONLY_PUBLIC_VECTOR":
            failures.append({"label": vector.get("label"), "source": vector.get("source")})
        if vector.get("warning") != "TEST_ONLY_PUBLIC_VECTOR_DO_NOT_USE_FOR_FUNDS":
            failures.append({"label": vector.get("label"), "warning": vector.get("warning")})
        address = vector.get("tron_base58_address", "")
        if vector.get("prefix2") != address[:DEFAULT_PREFIX_LEN]:
            failures.append({"label": vector.get("label"), "prefix2": "mismatch"})
        if vector.get("suffix5") != address[-DEFAULT_SUFFIX_LEN:]:
            failures.append({"label": vector.get("label"), "suffix5": "mismatch"})
    return {
        "vectors": len(vectors),
        "passed": len(failures) == 0,
        "failures": failures,
    }


def cuda_arch_candidates() -> List[str]:
    explicit = os.environ.get("CUDA_ARCH", "").strip()
    fallback_raw = os.environ.get("CUDA_ARCH_FALLBACKS", "").strip()
    raw_candidates = [explicit] if explicit else []
    if fallback_raw:
        raw_candidates.extend(part.strip() for part in fallback_raw.split(","))
    else:
        raw_candidates.extend(DEFAULT_CUDA_ARCH_FALLBACKS)

    candidates: List[str] = []
    for candidate in raw_candidates:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates or ["native"]


def nvcc_command_for_arch(arch: str) -> List[str]:
    return [
        "nvcc",
        "-std=c++17",
        "-O2",
        f"-arch={arch}",
        str(GPU_SOURCE_PATH),
        "-o",
        str(GPU_BINARY_PATH),
    ]


def compile_gpu_binary_if_allowed(timeout_seconds: int = 120) -> Dict[str, Any]:
    if GPU_BINARY_PATH.exists():
        return {
            "compiled": False,
            "ready": True,
            "reason": "GPU binary already exists.",
            "binary": str(GPU_BINARY_PATH),
        }
    if os.environ.get("ALLOW_RUNTIME_NVCC") != "1":
        return {
            "compiled": False,
            "ready": False,
            "reason": "GPU binary missing and ALLOW_RUNTIME_NVCC is not set.",
            "binary": str(GPU_BINARY_PATH),
        }

    GPU_BINARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    for arch in cuda_arch_candidates():
        command = nvcc_command_for_arch(arch)
        started = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(ROOT),
            )
        except FileNotFoundError:
            return {
                "compiled": False,
                "ready": False,
                "reason": "nvcc not found in worker image.",
                "binary": str(GPU_BINARY_PATH),
                "arch_attempts": attempts,
            }
        except subprocess.TimeoutExpired:
            attempts.append({
                "arch": arch,
                "returncode": None,
                "elapsed_seconds": timeout_seconds,
                "stderr": "nvcc compile timed out",
            })
            continue

        attempt = {
            "arch": arch,
            "returncode": result.returncode,
            "elapsed_seconds": time.perf_counter() - started,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:],
        }
        attempts.append(attempt)
        if result.returncode == 0 and GPU_BINARY_PATH.exists():
            return {
                "compiled": True,
                "ready": True,
                "returncode": result.returncode,
                "selected_arch": arch,
                "elapsed_seconds": attempt["elapsed_seconds"],
                "binary": str(GPU_BINARY_PATH),
                "arch_attempts": attempts,
            }

    return {
        "compiled": False,
        "ready": False,
        "reason": "nvcc compile failed for all CUDA arch candidates.",
        "binary": str(GPU_BINARY_PATH),
        "arch_attempts": attempts,
    }


def run_gpu_binary(args: List[str], timeout_seconds: int) -> Dict[str, Any]:
    if not GPU_BINARY_PATH.exists():
        return {
            "ready": False,
            "error": "GPU binary is not built yet.",
            "binary": str(GPU_BINARY_PATH),
        }
    try:
        result = subprocess.run(
            [str(GPU_BINARY_PATH), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "ready": True,
            "returncode": None,
            "error": "GPU binary timed out.",
            "binary": str(GPU_BINARY_PATH),
        }
    return {
        "ready": True,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def parse_json_stdout(status: Dict[str, Any]) -> Dict[str, Any]:
    stdout = status.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return {}
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def handle_health() -> Dict[str, Any]:
    vector_status = validate_vector_file()
    return {
        "mode": "health",
        "ready_for_gpu_benchmark": False,
        "gpu_binary_exists": GPU_BINARY_PATH.exists(),
        "runtime_nvcc_enabled": os.environ.get("ALLOW_RUNTIME_NVCC") == "1",
        "cuda_arch_candidates": cuda_arch_candidates(),
        "phase0_vectors": vector_status,
        "notes": [
            "This wrapper exists, but the CUDA core must pass vector alignment before speed tests.",
            "No key material or credential material is returned.",
        ],
    }


def handle_validate_vectors() -> Dict[str, Any]:
    vector_status = validate_vector_file()
    compile_status = compile_gpu_binary_if_allowed()
    binary_status = run_gpu_binary(["--validate-vectors", str(TEST_VECTOR_PATH)], timeout_seconds=30)
    vector_result = parse_json_stdout(binary_status)
    return {
        "mode": "validate_vectors",
        "phase0_vectors": vector_status,
        "compile": compile_status,
        "gpu_binary": binary_status,
        "gpu_result": vector_result,
        "passed": vector_status["passed"] and binary_status.get("returncode") == 0,
        "notes": [
            "This mode is a correctness gate, not a benchmark.",
            "Test private keys are public TEST_ONLY vectors and must not be used for funds.",
            "Benchmarking remains blocked until the GPU binary exists and passes this gate.",
        ],
    }


def handle_benchmark(payload: Dict[str, Any]) -> Dict[str, Any]:
    if os.environ.get("ALLOW_GPU_BENCHMARK") != "1":
        return {
            "mode": "benchmark",
            "allowed": False,
            "error": "GPU benchmark disabled. Set ALLOW_GPU_BENCHMARK=1 only inside an approved RunPod test.",
            "notes": [
                "This prevents accidental benchmark runs on 47.80.70.211 or local machines.",
                "Do not use CPU correctness or hash-only speed as TRON address generation speed.",
            ],
        }

    duration_seconds = int(payload.get("duration_seconds", 5))
    duration_seconds = max(1, min(duration_seconds, MAX_BENCHMARK_SECONDS))
    max_attempts = int(payload.get("max_attempts", 1024))
    max_attempts = max(1, min(max_attempts, MAX_BENCHMARK_ATTEMPTS))
    start_counter = int(payload.get("start_counter", 0))
    shard_id = int(payload.get("shard_id", 0))
    shard_count = int(payload.get("shard_count", 1))
    kernel_mode = payload.get("kernel_mode", "incremental")
    target_address = payload.get("target_address")
    prefix_len = int(payload.get("prefix_len", DEFAULT_PREFIX_LEN))
    suffix_len = int(payload.get("suffix_len", DEFAULT_SUFFIX_LEN))
    if (
        not isinstance(target_address, str)
        or not target_address.startswith("T")
        or not 26 <= len(target_address) <= 40
        or any(ch not in BASE58_ALPHABET for ch in target_address)
    ):
        raise ValueError("target_address must be a reasonable TRON Base58 address string starting with T")
    if shard_count < 1 or shard_id < 0 or shard_id >= shard_count:
        raise ValueError("invalid shard_id/shard_count")
    if start_counter < 0:
        raise ValueError("start_counter must be non-negative")
    if prefix_len < 0 or suffix_len < 0 or prefix_len + suffix_len > len(target_address):
        raise ValueError("invalid prefix_len/suffix_len")
    if kernel_mode not in {"incremental", "scalar"}:
        raise ValueError("kernel_mode must be incremental or scalar")

    compile_status = compile_gpu_binary_if_allowed()
    if not compile_status.get("ready"):
        return {
            "mode": "benchmark",
            "allowed": True,
            "compile": compile_status,
            "error": "GPU binary is not ready.",
            "notes": [
                "Benchmark remains blocked until the CUDA binary exists.",
                "No key material or credential material is returned.",
            ],
        }

    args = [
        "--benchmark",
        "--kernel-mode",
        kernel_mode,
        "--target-address",
        target_address,
        "--prefix-len",
        str(prefix_len),
        "--suffix-len",
        str(suffix_len),
        "--duration-seconds",
        str(duration_seconds),
        "--max-attempts",
        str(max_attempts),
        "--start-counter",
        str(start_counter),
        "--shard-id",
        str(shard_id),
        "--shard-count",
        str(shard_count),
    ]
    started = time.perf_counter()
    binary_status = run_gpu_binary(args, timeout_seconds=duration_seconds + 15)
    benchmark_result = parse_json_stdout(binary_status)
    elapsed = time.perf_counter() - started
    return {
        "mode": "benchmark",
        "duration_seconds": duration_seconds,
        "max_attempts": max_attempts,
        "start_counter": start_counter,
        "shard_id": shard_id,
        "shard_count": shard_count,
        "kernel_mode": kernel_mode,
        "elapsed_seconds": elapsed,
        "compile": compile_status,
        "gpu_binary": binary_status,
        "benchmark_result": benchmark_result,
        "notes": [
            "Benchmark output must report complete TRON addresses_per_second.",
            "Benchmark mode must not return key material.",
        ],
    }


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("input", event)
    mode = payload.get("mode", "health")
    started_at = utc_now_iso()
    try:
        if mode == "health":
            result = handle_health()
        elif mode == "validate_vectors":
            result = handle_validate_vectors()
        elif mode == "benchmark":
            result = handle_benchmark(payload)
        else:
            raise ValueError(f"unsupported mode: {mode}")
        result["started_at"] = started_at
        result["finished_at"] = utc_now_iso()
        return result
    except Exception as exc:
        return {
            "mode": mode,
            "error": str(exc),
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "notes": [
                "No key material or credential material is returned.",
            ],
        }


if __name__ == "__main__":
    if runpod is None:
        print(json.dumps(handle_health(), indent=2))
    else:
        runpod.serverless.start({"handler": handler})
