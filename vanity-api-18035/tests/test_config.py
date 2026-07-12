from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vanity18035.config import ConfigError

from .helpers import test_settings


class ConfigTests(unittest.TestCase):
    def test_loopback_test_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            test_settings(Path(directory) / "state.sqlite3").validate()

    def test_wrong_port_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = test_settings(Path(directory) / "state.sqlite3", port=18030)
            with self.assertRaises(ConfigError):
                settings.validate()

    def test_production_database_is_rejected(self) -> None:
        protected_path = Path("/opt") / ("vanity-" + "address-api") / "state.sqlite3"
        settings = test_settings(protected_path)
        with self.assertRaises(ConfigError):
            settings.validate()

    def test_public_plaintext_listener_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = test_settings(
                Path(directory) / "state.sqlite3",
                host="0.0.0.0",
                allow_insecure_local=True,
            )
            with self.assertRaises(ConfigError):
                settings.validate()

    def test_production_requires_expected_worker_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = test_settings(
                Path(directory) / "state.sqlite3",
                environment="production",
                host="0.0.0.0",
                customer_allowed_ips=frozenset({"192.0.2.1"}),
                worker_allowed_ips=frozenset({"192.0.2.2"}),
                worker_id="",
                callback_url="https://customer.example/callback",
                age_recipient="age1test",
                tls_cert_path=Path(directory) / "server.crt",
                tls_key_path=Path(directory) / "server.key",
                worker_ca_path=Path(directory) / "worker-ca.crt",
                require_worker_mtls=True,
            )
            with self.assertRaises(ConfigError):
                settings.validate()


if __name__ == "__main__":
    unittest.main()
