from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vanity18035.config import ConfigError
from vanity18035.worker_config import WorkerSettings


def settings(directory: str, **overrides: object) -> WorkerSettings:
    values = {
        "environment": "test",
        "worker_id": "worker-0001",
        "controller_url": "http://127.0.0.1:18035",
        "state_db_path": Path(directory) / "worker.sqlite3",
        "core_socket_path": Path(directory) / "core.sock",
        "age_recipient": "",
        "tls_ca_path": None,
        "tls_cert_path": None,
        "tls_key_path": None,
        "allow_insecure_local": True,
        "heartbeat_seconds": 1.0,
        "reconnect_min_seconds": 0.1,
        "reconnect_max_seconds": 5.0,
    }
    values.update(overrides)
    return WorkerSettings(**values)


class WorkerConfigTests(unittest.TestCase):
    def test_loopback_development_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings(directory).validate()

    def test_public_plaintext_controller_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            value = settings(directory, controller_url="http://example.com:18035")
            with self.assertRaises(ConfigError):
                value.validate()

    def test_production_requires_mtls_materials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            value = settings(
                directory,
                environment="production",
                controller_url="https://example.com:18035",
                allow_insecure_local=False,
            )
            with self.assertRaises(ConfigError):
                value.validate()


if __name__ == "__main__":
    unittest.main()
