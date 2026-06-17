#!/usr/bin/env python3
"""Verify production find response returns only age ciphertext, not plaintext key material."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app


FORBIDDEN_RESPONSE_MARKERS = [
    "private_key_hex",
    "mnemonic",
    "seed",
    "token",
    "secret",
    "wif",
]


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def collect_forbidden_markers(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}"
            if key != "encrypted_private_key":
                lowered_key = key.lower()
                for marker in FORBIDDEN_RESPONSE_MARKERS:
                    if marker in lowered_key:
                        hits.append(f"{key_path}: key contains {marker}")
            hits.extend(collect_forbidden_markers(item, key_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(collect_forbidden_markers(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        lowered = value.lower()
        if path.endswith(".encrypted_private_key"):
            return hits
        for marker in FORBIDDEN_RESPONSE_MARKERS:
            if marker in lowered:
                hits.append(f"{path}: value contains {marker}")
    return hits


def main() -> int:
    original_binary_path = app.GPU_BINARY_PATH
    original_vanitysearch_path = app.VANITYSEARCH_BINARY_PATH
    original_path = os.environ.get("PATH", "")
    original_find = os.environ.get("ALLOW_GPU_FIND")
    original_backend = os.environ.get("GPU_WORKER_BACKEND")
    private_key_hex = "0" * 63 + "1"
    responses: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="tron-find-contract-") as tmp:
        tmp_path = Path(tmp)
        fake_gpu = tmp_path / "tron_gpu_worker"
        fake_vanitysearch = tmp_path / "vanitysearch_tron_worker"
        fake_age = tmp_path / "age"
        write_executable(
            fake_gpu,
            "#!/usr/bin/env python3\n"
            "import json\n"
            f"print(json.dumps({{'mode':'find','matched':True,'matched_address':'TA11111111111111111111111111CDEFG','private_key_hex':'{private_key_hex}','attempts':1,'gpu_name':'FAKE_GPU'}}))\n",
        )
        write_executable(
            fake_vanitysearch,
            "#!/usr/bin/env python3\n"
            "import json\n"
            f"print(json.dumps({{'mode':'tron_find','matched':True,'matched_address':'TA11111111111111111111111111CDEFG','private_key_hex':'{private_key_hex}'}}))\n",
        )
        write_executable(
            fake_age,
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "_ = sys.stdin.read()\n"
            "print('-----BEGIN AGE ENCRYPTED FILE-----')\n"
            "print('YWdlLWVuY3J5cHRlZC10ZXN0LWNpcGhlcnRleHQ=')\n"
            "print('-----END AGE ENCRYPTED FILE-----')\n",
        )

        app.GPU_BINARY_PATH = fake_gpu
        app.VANITYSEARCH_BINARY_PATH = fake_vanitysearch
        os.environ["PATH"] = str(tmp_path) + os.pathsep + original_path
        os.environ["ALLOW_GPU_FIND"] = "1"
        try:
            for backend in ("self", "vanitysearch"):
                os.environ["GPU_WORKER_BACKEND"] = backend
                responses.append(
                    app.handle_find(
                        {
                            "suffix": "CDEFG",
                            "age_recipient": "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
                            "duration_seconds": 1,
                            "max_attempts": 1,
                            "start_counter": 0,
                            "shard_id": 0,
                            "shard_count": 1,
                        }
                    )
                )
        finally:
            app.GPU_BINARY_PATH = original_binary_path
            app.VANITYSEARCH_BINARY_PATH = original_vanitysearch_path
            os.environ["PATH"] = original_path
            if original_find is None:
                os.environ.pop("ALLOW_GPU_FIND", None)
            else:
                os.environ["ALLOW_GPU_FIND"] = original_find
            if original_backend is None:
                os.environ.pop("GPU_WORKER_BACKEND", None)
            else:
                os.environ["GPU_WORKER_BACKEND"] = original_backend

    failures = []
    for index, response in enumerate(responses):
        backend = response.get("gpu_worker_backend", "self")
        if response.get("matched") is not True:
            failures.append(f"{backend}: find response did not match")
        if response.get("matched_address") != "TA11111111111111111111111111CDEFG":
            failures.append(f"{backend}: matched_address mismatch")
        encrypted = response.get("encrypted_private_key")
        if not isinstance(encrypted, str) or not encrypted.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
            failures.append(f"{backend}: missing age ciphertext")
        failures.extend(f"{backend}: {failure}" for failure in collect_forbidden_markers(response))

    print(
        json.dumps(
            {
                "mode": "verify_find_response_contract",
                "passed": not failures,
                "failures": failures,
                "backends": [response.get("gpu_worker_backend", "self") for response in responses],
                "response_keys": [sorted(response.keys()) for response in responses],
                "notes": [
                    "Uses fake local GPU workers and fake local age binary only.",
                    "Verifies API response has age ciphertext and no plaintext key markers.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
