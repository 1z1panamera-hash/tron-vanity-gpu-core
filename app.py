import json
import os
import re
import shutil
import shlex
import subprocess
import tempfile
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
VANITYSEARCH_BINARY_PATH = ROOT / "build" / "vanitysearch_tron_worker"
GPU_SOURCE_PATH = ROOT / "src" / "tron_gpu_core.cu"
DEFAULT_PREFIX_LEN = 0
DEFAULT_SUFFIX_LEN = 5
DEFAULT_TRON_ADDRESS_LEN = 34
MAX_BENCHMARK_SECONDS = 10
MAX_FIND_SECONDS = 15
MAX_BENCHMARK_ATTEMPTS = 10_000_000_000
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
DEFAULT_CUDA_ARCH_FALLBACKS = ["native", "sm_120", "sm_80"]
SENSITIVE_OUTPUT_RE = re.compile(r"Priv|WIF|HEX|private_key|mnemonic|seed|token|secret", re.IGNORECASE)
VANITYSEARCH_SPEED_RE = re.compile(r"\[([0-9.]+) Mkey/s\]\[GPU ([0-9.]+) Mkey/s\]")


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
        if vector.get("prefix2") != address[:2]:
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


def synthesize_target_address(suffix: str) -> str:
    if not isinstance(suffix, str) or len(suffix) != DEFAULT_SUFFIX_LEN:
        raise ValueError("suffix must be exactly 5 Base58 characters")
    if any(ch not in BASE58_ALPHABET for ch in suffix):
        raise ValueError("suffix contains a non-Base58 character")

    filler_len = DEFAULT_TRON_ADDRESS_LEN - 1 - len(suffix)
    if filler_len < 0:
        raise ValueError("invalid target rule length")
    return "T" + ("8" * filler_len) + suffix


def normalize_match_rule(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "prefix_after_t" in payload:
        raise ValueError("product rule is suffix-only; prefix_after_t is no longer accepted")

    if "suffix" in payload:
        suffix = payload.get("suffix")
        target_address = synthesize_target_address(suffix)
        return {
            "target_address": target_address,
            "prefix_len": DEFAULT_PREFIX_LEN,
            "suffix_len": DEFAULT_SUFFIX_LEN,
            "suffix": suffix,
            "effective_random_chars": DEFAULT_SUFFIX_LEN,
            "search_space": 58 ** DEFAULT_SUFFIX_LEN,
            "rule": "TRON suffix-only last 5 Base58 characters",
        }

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
    if prefix_len != DEFAULT_PREFIX_LEN or suffix_len != DEFAULT_SUFFIX_LEN:
        raise ValueError("product rule requires suffix-only prefix_len=0 and suffix_len=5")
    return {
        "target_address": target_address,
        "prefix_len": prefix_len,
        "suffix_len": suffix_len,
        "suffix": target_address[-suffix_len:],
        "effective_random_chars": suffix_len,
        "search_space": 58 ** suffix_len,
        "rule": "TRON suffix-only last 5 Base58 characters",
    }


def selected_gpu_backend() -> str:
    explicit = os.environ.get("GPU_WORKER_BACKEND", "").strip().lower()
    if explicit:
        if explicit not in {"self", "vanitysearch"}:
            raise ValueError("GPU_WORKER_BACKEND must be self or vanitysearch")
        return explicit
    if VANITYSEARCH_BINARY_PATH.exists():
        return "vanitysearch"
    return "self"


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


def run_gpu_binary_internal(args: List[str], timeout_seconds: int) -> Dict[str, Any]:
    """Run CUDA binary for production find path without echoing stdout to API."""
    if not GPU_BINARY_PATH.exists():
        return {
            "ready": False,
            "returncode": None,
            "error": "GPU binary is not built yet.",
            "binary": str(GPU_BINARY_PATH),
            "parsed": {},
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
            "parsed": {},
        }

    parsed: Dict[str, Any] = {}
    try:
        loaded = json.loads(result.stdout) if result.stdout.strip() else {}
        if isinstance(loaded, dict):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = {}

    return {
        "ready": True,
        "returncode": result.returncode,
        "stderr": result.stderr[-2000:],
        "binary": str(GPU_BINARY_PATH),
        "parsed": parsed,
    }


def strip_allowed_safety_markers(text: str) -> str:
    return text.replace("TRON_SUPPRESS_SECRET_OUTPUT", "")


def contains_forbidden_output_marker(text: str) -> bool:
    return bool(SENSITIVE_OUTPUT_RE.search(strip_allowed_safety_markers(text)))


def parse_vanitysearch_speed(stdout: str) -> Dict[str, Any]:
    matches = VANITYSEARCH_SPEED_RE.findall(stdout)
    if not matches:
        return {
            "passed": False,
            "error": "no VanitySearch Mkey/s sample found",
            "samples": 0,
        }
    total_mkey_s, gpu_mkey_s = (float(value) for value in matches[-1])
    return {
        "passed": True,
        "samples": len(matches),
        "reported_total_mkey_s": total_mkey_s,
        "reported_gpu_mkey_s": gpu_mkey_s,
        "candidate_attempts_per_second_estimate": gpu_mkey_s * 1_000_000.0,
    }


def run_vanitysearch_benchmark(suffix: str, duration_seconds: int, gpu_grid: str) -> Dict[str, Any]:
    if not VANITYSEARCH_BINARY_PATH.exists():
        return {
            "ready": False,
            "error": "patched VanitySearch TRON worker is not built yet.",
            "binary": str(VANITYSEARCH_BINARY_PATH),
        }
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{5}", suffix):
        raise ValueError("suffix must be exactly 5 Base58 characters")
    if not re.fullmatch(r"[0-9]+,[0-9]+", gpu_grid):
        raise ValueError("gpu_grid must use VanitySearch format like 128,128")

    pattern = f"T*{suffix}"
    env = os.environ.copy()
    env["TRON_SUPPRESS_SECRET_OUTPUT"] = "1"
    command = [
        str(VANITYSEARCH_BINARY_PATH),
        "-gpu",
        "-t",
        "0",
        "-g",
        gpu_grid,
        pattern,
    ]

    stdout = ""
    stderr = ""
    returncode = None
    script_bin = shutil.which("script")
    timeout_bin = shutil.which("timeout")
    if script_bin and timeout_bin:
        with tempfile.NamedTemporaryFile(prefix="vanitysearch-benchmark-", suffix=".log") as capture:
            shell_cmd = " ".join(shlex.quote(part) for part in [timeout_bin, f"{duration_seconds}s", *command])
            result = subprocess.run(
                [script_bin, "-q", "-e", "-c", shell_cmd, capture.name],
                check=False,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 20,
                env=env,
            )
            returncode = result.returncode
            stderr = result.stderr[-2000:]
            stdout = Path(capture.name).read_text(errors="ignore")
    else:
        result = subprocess.run(
            [timeout_bin or "timeout", f"{duration_seconds}s", *command],
            check=False,
            capture_output=True,
            text=True,
            timeout=duration_seconds + 20,
            env=env,
        )
        returncode = result.returncode
        stdout = result.stdout
        stderr = result.stderr

    if returncode not in {0, 124}:
        return {
            "ready": True,
            "returncode": returncode,
            "error": "patched VanitySearch benchmark failed",
            "binary": str(VANITYSEARCH_BINARY_PATH),
            "stderr_tail": stderr[-2000:],
        }
    if contains_forbidden_output_marker(stdout) or contains_forbidden_output_marker(stderr):
        return {
            "ready": True,
            "returncode": returncode,
            "error": "patched VanitySearch emitted a forbidden key marker",
            "binary": str(VANITYSEARCH_BINARY_PATH),
        }

    parsed = parse_vanitysearch_speed(stdout)
    parsed.update({
        "ready": True,
        "returncode": returncode,
        "timeout_reached": returncode == 124,
        "binary": str(VANITYSEARCH_BINARY_PATH),
        "pattern": pattern,
        "gpu_grid": gpu_grid,
    })
    return parsed


def parse_vanitysearch_find_stdout(stdout: str, suffix: str) -> Dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(candidate, dict) or candidate.get("mode") != "tron_find":
            continue

        matched_address = candidate.get("matched_address")
        private_key_hex = candidate.get("private_key_hex")
        if candidate.get("matched") is not True:
            continue
        if (
            not isinstance(matched_address, str)
            or not matched_address.startswith("T")
            or not matched_address.endswith(suffix)
            or any(ch not in BASE58_ALPHABET for ch in matched_address)
        ):
            raise ValueError("patched VanitySearch returned an invalid matched_address")
        if not isinstance(private_key_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", private_key_hex):
            raise ValueError("patched VanitySearch returned an invalid internal key value")
        return {
            "matched": True,
            "matched_address": matched_address,
            "private_key_hex": private_key_hex.lower(),
        }
    return {"matched": False}


def run_vanitysearch_find_internal(suffix: str, duration_seconds: int, gpu_grid: str) -> Dict[str, Any]:
    """Run patched VanitySearch find mode and keep raw stdout internal-only."""
    if not VANITYSEARCH_BINARY_PATH.exists():
        return {
            "ready": False,
            "returncode": None,
            "error": "patched VanitySearch TRON worker is not built yet.",
            "binary": str(VANITYSEARCH_BINARY_PATH),
            "parsed": {},
        }
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{5}", suffix):
        raise ValueError("suffix must be exactly 5 Base58 characters")
    if not re.fullmatch(r"[0-9]+,[0-9]+", gpu_grid):
        raise ValueError("gpu_grid must use VanitySearch format like 128,128")

    pattern = f"T*{suffix}"
    env = os.environ.copy()
    env["TRON_JSON_HIT_OUTPUT"] = "1"
    command = [
        str(VANITYSEARCH_BINARY_PATH),
        "-gpu",
        "-stop",
        "-t",
        "0",
        "-g",
        gpu_grid,
        pattern,
    ]
    timeout_bin = shutil.which("timeout")
    effective_command = [timeout_bin, f"{duration_seconds}s", *command] if timeout_bin else command

    try:
        result = subprocess.run(
            effective_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=duration_seconds + 20,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "ready": True,
            "returncode": None,
            "timeout": True,
            "binary": str(VANITYSEARCH_BINARY_PATH),
            "parsed": {"matched": False},
        }

    if re.search(r"Priv \(|WIF|mnemonic|seed|token|secret", result.stdout + result.stderr, re.IGNORECASE):
        return {
            "ready": True,
            "returncode": result.returncode,
            "error": "patched VanitySearch emitted an unsafe output marker",
            "binary": str(VANITYSEARCH_BINARY_PATH),
            "parsed": {},
        }

    parsed = parse_vanitysearch_find_stdout(result.stdout, suffix)
    return {
        "ready": True,
        "returncode": result.returncode,
        "timeout": result.returncode == 124,
        "binary": str(VANITYSEARCH_BINARY_PATH),
        "parsed": parsed,
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


def validate_age_recipient(recipient: Any) -> str:
    if not isinstance(recipient, str) or not recipient.startswith("age1"):
        raise ValueError("age_recipient must be an age recipient public key beginning with age1")
    if len(recipient) < 20 or len(recipient) > 200:
        raise ValueError("age_recipient length is invalid")
    allowed = set("qpzry9x8gf2tvdw0s3jn54khce6mua7l")
    if any(ch not in allowed for ch in recipient[4:]):
        raise ValueError("age_recipient contains invalid characters")
    return recipient


def encrypt_private_key_with_age(private_key_hex: str, age_recipient: str) -> str:
    if not isinstance(private_key_hex, str) or len(private_key_hex) != 64:
        raise ValueError("internal private key must be 64 hex characters")
    try:
        int(private_key_hex, 16)
    except ValueError as exc:
        raise ValueError("internal private key is not hex") from exc

    try:
        result = subprocess.run(
            ["age", "-a", "-r", age_recipient],
            input=private_key_hex + "\n",
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("age binary not found in worker image") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("age encryption timed out") from exc

    if result.returncode != 0:
        raise RuntimeError("age encryption failed")
    encrypted = result.stdout.strip()
    if not encrypted.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
        raise RuntimeError("age encryption output is invalid")
    return encrypted


def handle_health() -> Dict[str, Any]:
    vector_status = validate_vector_file()
    return {
        "mode": "health",
        "ready_for_gpu_benchmark": False,
        "gpu_worker_backend": selected_gpu_backend(),
        "gpu_binary_exists": GPU_BINARY_PATH.exists(),
        "vanitysearch_binary_exists": VANITYSEARCH_BINARY_PATH.exists(),
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
    gpu_backend = selected_gpu_backend()
    match_rule = normalize_match_rule(payload)
    target_address = match_rule["target_address"]
    prefix_len = match_rule["prefix_len"]
    suffix_len = match_rule["suffix_len"]
    if shard_count < 1 or shard_id < 0 or shard_id >= shard_count:
        raise ValueError("invalid shard_id/shard_count")
    if start_counter < 0:
        raise ValueError("start_counter must be non-negative")
    if prefix_len < 0 or suffix_len < 0 or prefix_len + suffix_len > len(target_address):
        raise ValueError("invalid prefix_len/suffix_len")
    if kernel_mode not in {"incremental", "scalar"}:
        raise ValueError("kernel_mode must be incremental or scalar")

    if gpu_backend == "vanitysearch":
        gpu_grid = str(payload.get("gpu_grid", "128,128"))
        started = time.perf_counter()
        benchmark_result = run_vanitysearch_benchmark(match_rule["suffix"], duration_seconds, gpu_grid)
        elapsed = time.perf_counter() - started
        return {
            "mode": "benchmark",
            "gpu_worker_backend": gpu_backend,
            "duration_seconds": duration_seconds,
            "max_attempts": max_attempts,
            "match_rule": match_rule,
            "gpu_grid": gpu_grid,
            "elapsed_seconds": elapsed,
            "benchmark_result": benchmark_result,
            "notes": [
                "Patched VanitySearch benchmark mode suppresses sensitive output and returns only speed metadata.",
                "This is for Serverless smoke/performance proof; production find uses a separate JSON hit protocol and age-encrypted return path.",
            ],
        }

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
    binary_status = run_gpu_binary(args, timeout_seconds=duration_seconds + 120)
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
        "match_rule": match_rule,
        "elapsed_seconds": elapsed,
        "compile": compile_status,
        "gpu_binary": binary_status,
        "benchmark_result": benchmark_result,
        "notes": [
            "Benchmark output must report complete TRON addresses_per_second.",
            "Benchmark mode must not return key material.",
        ],
    }


def handle_find(payload: Dict[str, Any]) -> Dict[str, Any]:
    if os.environ.get("ALLOW_GPU_FIND") != "1":
        return {
            "mode": "find",
            "allowed": False,
            "error": "GPU find disabled. Set ALLOW_GPU_FIND=1 only inside an approved RunPod production worker.",
            "notes": [
                "This prevents accidental private-key generation on local machines or 47.80.70.211.",
                "Production mode must return only matched_address and encrypted_private_key.",
            ],
        }

    age_recipient = validate_age_recipient(payload.get("age_recipient"))
    match_rule = normalize_match_rule(payload)
    gpu_backend = selected_gpu_backend()
    duration_seconds = int(payload.get("duration_seconds", MAX_FIND_SECONDS))
    duration_seconds = max(1, min(duration_seconds, MAX_FIND_SECONDS))
    max_attempts = int(payload.get("max_attempts", MAX_BENCHMARK_ATTEMPTS))
    max_attempts = max(1, min(max_attempts, MAX_BENCHMARK_ATTEMPTS))
    start_counter = int(payload.get("start_counter", 0))
    shard_id = int(payload.get("shard_id", 0))
    shard_count = int(payload.get("shard_count", 1))
    if shard_count < 1 or shard_id < 0 or shard_id >= shard_count:
        raise ValueError("invalid shard_id/shard_count")
    if start_counter < 0:
        raise ValueError("start_counter must be non-negative")

    if gpu_backend == "vanitysearch":
        gpu_grid = str(payload.get("gpu_grid", "128,128"))
        started = time.perf_counter()
        binary_status = run_vanitysearch_find_internal(match_rule["suffix"], duration_seconds, gpu_grid)
        elapsed = time.perf_counter() - started
        gpu_result = binary_status.get("parsed", {})

        if not binary_status.get("ready") or binary_status.get("error"):
            return {
                "mode": "find",
                "allowed": True,
                "matched": False,
                "gpu_worker_backend": gpu_backend,
                "match_rule": match_rule,
                "elapsed_seconds": elapsed,
                "gpu_binary": {
                    "ready": binary_status.get("ready"),
                    "returncode": binary_status.get("returncode"),
                    "binary": binary_status.get("binary"),
                },
                "error": binary_status.get("error", "patched VanitySearch find failed"),
                "notes": [
                    "No sensitive material is returned.",
                ],
            }

        if not gpu_result.get("matched"):
            return {
                "mode": "find",
                "allowed": True,
                "matched": False,
                "gpu_worker_backend": gpu_backend,
                "match_rule": match_rule,
                "elapsed_seconds": elapsed,
                "gpu_grid": gpu_grid,
                "notes": [
                    "No match found within this bounded RunPod invocation.",
                    "No sensitive material is returned.",
                ],
            }

        encrypted_private_key = encrypt_private_key_with_age(gpu_result.get("private_key_hex"), age_recipient)
        return {
            "mode": "find",
            "allowed": True,
            "matched": True,
            "gpu_worker_backend": gpu_backend,
            "matched_address": gpu_result.get("matched_address"),
            "encrypted_private_key": encrypted_private_key,
            "match_rule": match_rule,
            "elapsed_seconds": elapsed,
            "gpu_grid": gpu_grid,
            "notes": [
                "Sensitive material was encrypted with the customer age recipient before returning.",
                "Response intentionally omits raw key material and credential material.",
            ],
        }

    compile_status = compile_gpu_binary_if_allowed()
    if not compile_status.get("ready"):
        return {
            "mode": "find",
            "allowed": True,
            "compile": compile_status,
            "error": "GPU binary is not ready.",
            "notes": [
                "Find remains blocked until the CUDA binary exists.",
                "No key material or credential material is returned.",
            ],
        }

    args = [
        "--find",
        "--target-address",
        match_rule["target_address"],
        "--prefix-len",
        str(match_rule["prefix_len"]),
        "--suffix-len",
        str(match_rule["suffix_len"]),
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
    binary_status = run_gpu_binary_internal(args, timeout_seconds=duration_seconds + 120)
    elapsed = time.perf_counter() - started
    gpu_result = binary_status.get("parsed", {})

    if binary_status.get("returncode") != 0:
        return {
            "mode": "find",
            "allowed": True,
            "matched": False,
            "match_rule": match_rule,
            "elapsed_seconds": elapsed,
            "compile": compile_status,
            "gpu_binary": {
                "ready": binary_status.get("ready"),
                "returncode": binary_status.get("returncode"),
                "stderr": binary_status.get("stderr"),
                "binary": binary_status.get("binary"),
            },
            "error": binary_status.get("error", "GPU find failed or is not implemented."),
            "notes": [
                "No plaintext private key is returned.",
            ],
        }

    matched = bool(gpu_result.get("matched"))
    matched_address = gpu_result.get("matched_address", "")
    if not matched:
        return {
            "mode": "find",
            "allowed": True,
            "matched": False,
            "match_rule": match_rule,
            "elapsed_seconds": elapsed,
            "attempts": gpu_result.get("attempts"),
            "gpu_name": gpu_result.get("gpu_name"),
            "notes": [
                "No match found within this bounded RunPod invocation.",
                "No key material is returned.",
            ],
        }

    if not isinstance(matched_address, str) or not matched_address.startswith("T"):
        raise ValueError("GPU result matched_address is invalid")
    private_key_hex = gpu_result.get("private_key_hex")
    encrypted_private_key = encrypt_private_key_with_age(private_key_hex, age_recipient)
    return {
        "mode": "find",
        "allowed": True,
        "matched": True,
        "matched_address": matched_address,
        "encrypted_private_key": encrypted_private_key,
        "match_rule": match_rule,
        "elapsed_seconds": elapsed,
        "attempts": gpu_result.get("attempts"),
        "gpu_name": gpu_result.get("gpu_name"),
        "notes": [
            "Sensitive material was encrypted with the customer age recipient before returning.",
            "Response intentionally omits raw key material and credential material.",
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
        elif mode == "find":
            result = handle_find(payload)
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
