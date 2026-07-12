#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from vanity18035.config import Settings
from vanity18035.worker_config import WorkerSettings


PROTECTED = (
    "/opt/vanity-" + "address-api",
    "180" + "30",
    "180" + "31",
    "180" + "32",
)


def load_environment(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("environment file does not exist")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("environment file must not be accessible by group or other")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError("environment file contains an invalid line")
        key, value = stripped.split("=", 1)
        if not key.startswith("VANITY18035_") or not key.replace("_", "").isalnum():
            raise ValueError("environment file contains an unexpected key")
        if any(protected in value for protected in PROTECTED):
            raise ValueError("environment value crosses a protected production boundary")
        result[key] = value
    return result


def require_file(path: Path | None, *, private: bool = False) -> None:
    if path is None or not path.is_file():
        raise ValueError("a required deployment file is missing")
    if private and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("a private deployment file must have mode 0600 or stricter")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("controller", "worker"))
    parser.add_argument("environment_file", type=Path)
    args = parser.parse_args()

    values = load_environment(args.environment_file)
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        if args.role == "controller":
            settings = Settings.from_env()
            settings.validate()
            require_file(settings.tls_cert_path)
            require_file(settings.tls_key_path, private=True)
            require_file(settings.worker_ca_path)
            if settings.db_path.parent != Path("/opt/vanity-api-18035/data"):
                raise ValueError("controller database must use the isolated data directory")
        else:
            settings = WorkerSettings.from_env()
            settings.validate()
            require_file(settings.tls_ca_path)
            require_file(settings.tls_cert_path)
            require_file(settings.tls_key_path, private=True)
            if settings.state_db_path.parent != Path("/opt/vanity-api-18035/data"):
                raise ValueError("worker database must use the isolated data directory")
            if settings.core_socket_path != Path("/run/vanity-api-18035/core.sock"):
                raise ValueError("worker socket must use the isolated runtime directory")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(f"deployment_preflight role={args.role} status=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
