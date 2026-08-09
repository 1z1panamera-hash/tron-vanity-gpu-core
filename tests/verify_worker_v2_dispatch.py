#!/usr/bin/env python3
"""Offline checks for Worker v2 GPU-core selection and runtime fallback."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app


AGE_RECIPIENT = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"


def reset_gpu_cache() -> None:
    app.GPU_NAME_CACHE = None
    app.GPU_COMPUTE_CAPABILITY_CACHE = None


def assert_variant(name: str, capability: str, expected: str) -> None:
    os.environ["RUNPOD_GPU_NAME"] = name
    os.environ["RUNPOD_GPU_COMPUTE_CAPABILITY"] = capability
    reset_gpu_cache()
    actual = app.select_vanitysearch_core()["variant"]
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}")


def main() -> int:
    original_legacy = app.VANITYSEARCH_BINARY_PATH
    original_round51 = app.VANITYSEARCH_ROUND51_BINARY_PATH
    original_run_find = app.run_vanitysearch_find_internal
    original_encrypt = app.encrypt_private_key_with_age
    original_env = os.environ.copy()
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="runpod-worker-v2-dispatch-") as tmp:
        tmp_path = Path(tmp)
        legacy = tmp_path / "legacy"
        round51 = tmp_path / "round51"
        legacy.touch()
        round51.touch()
        app.VANITYSEARCH_BINARY_PATH = legacy
        app.VANITYSEARCH_ROUND51_BINARY_PATH = round51
        os.environ["GPU_WORKER_BACKEND"] = "auto"
        os.environ["VANITYSEARCH_CORE_VARIANT"] = "auto"

        try:
            assert_variant("NVIDIA GeForce RTX 5090", "12.0", "round51-sm120")
            assert_variant("NVIDIA RTX PRO 6000 Blackwell Server Edition", "12.0", "round51-sm120")
            assert_variant("NVIDIA GeForce RTX 4090", "8.9", "legacy-multiarch")
            if app.default_vanitysearch_gpu_grid("NVIDIA GeForce RTX 5090", "round51-sm120") != "160,128":
                failures.append("Round51 default GPU grid is not the validated 160,128 profile")

            round51.unlink()
            assert_variant("NVIDIA GeForce RTX 5090", "12.0", "legacy-multiarch")
            round51.touch()

            calls: list[Path] = []

            def fake_find(*args: Any, binary_path: Optional[Path] = None, **kwargs: Any) -> dict[str, Any]:
                selected = Path(binary_path or "")
                calls.append(selected)
                if selected == round51:
                    return {
                        "ready": True,
                        "returncode": 70,
                        "error": "optimized core failed",
                        "parsed": {},
                        "timings": {"binary_subprocess_seconds": 0.01},
                    }
                return {
                    "ready": True,
                    "returncode": 0,
                    "parsed": {
                        "matched": True,
                        "matched_address": "TA11111111111111111111111111CDEFG",
                        "private_key_hex": "0" * 63 + "1",
                    },
                    "safe_diagnostics": {},
                    "timings": {"binary_subprocess_seconds": 0.01},
                }

            app.run_vanitysearch_find_internal = fake_find
            app.encrypt_private_key_with_age = lambda *_: (
                "-----BEGIN AGE ENCRYPTED FILE-----\nTEST\n-----END AGE ENCRYPTED FILE-----"
            )
            os.environ["ALLOW_GPU_FIND"] = "1"
            os.environ["RUNPOD_GPU_NAME"] = "NVIDIA GeForce RTX 5090"
            os.environ["RUNPOD_GPU_COMPUTE_CAPABILITY"] = "12.0"
            reset_gpu_cache()
            response = app.handle_find(
                {
                    "suffix": "CDEFG",
                    "age_recipient": AGE_RECIPIENT,
                    "duration_seconds": 5,
                }
            )
            if calls != [round51, legacy]:
                failures.append(f"unexpected fallback call order: {calls}")
            if response.get("matched") is not True:
                failures.append("legacy fallback did not return the valid match")
            if response.get("gpu_core_variant") != "legacy-multiarch":
                failures.append("fallback response did not identify legacy core")
            if response.get("gpu_core_fallback_from") != "round51-sm120":
                failures.append("fallback source was not recorded")
            if "private_key_hex" in str(response):
                failures.append("plaintext key marker leaked into response")
        except Exception as exc:
            failures.append(str(exc))
        finally:
            app.VANITYSEARCH_BINARY_PATH = original_legacy
            app.VANITYSEARCH_ROUND51_BINARY_PATH = original_round51
            app.run_vanitysearch_find_internal = original_run_find
            app.encrypt_private_key_with_age = original_encrypt
            os.environ.clear()
            os.environ.update(original_env)
            reset_gpu_cache()

    print({"mode": "verify_worker_v2_dispatch", "passed": not failures, "failures": failures})
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
