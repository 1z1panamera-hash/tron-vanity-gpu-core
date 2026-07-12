from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from vanity18035.database import ControllerDatabase
from vanity18035.internal_auth import WorkerAuthenticator, WorkerAuthError

from .helpers import test_settings


class InternalAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = ControllerDatabase(Path(self.temp.name) / "controller.sqlite3")
        self.database.initialize()
        self.settings = test_settings(
            self.database.path,
            worker_allowed_ips=frozenset({"192.0.2.2"}),
            require_worker_mtls=True,
        )
        self.authenticator = WorkerAuthenticator(self.settings, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def payload(worker_id: str = "worker-0001") -> dict[str, object]:
        return {
            "worker_id": worker_id,
            "event_id": str(uuid.uuid4()),
            "nonce": uuid.uuid4().hex,
            "timestamp": time.time(),
        }

    @staticmethod
    def certificate(common_name: str) -> dict[str, object]:
        return {"subject": ((('commonName', common_name),),)}

    def test_worker_id_must_match_configured_id_and_certificate(self) -> None:
        identity = self.authenticator.verify(
            self.payload(),
            remote_ip="192.0.2.2",
            peer_certificate=self.certificate("worker-0001"),
        )
        self.assertEqual(identity.worker_id, "worker-0001")

        with self.assertRaises(WorkerAuthError):
            self.authenticator.verify(
                self.payload("worker-0002"),
                remote_ip="192.0.2.2",
                peer_certificate=self.certificate("worker-0002"),
            )

        with self.assertRaises(WorkerAuthError):
            self.authenticator.verify(
                self.payload(),
                remote_ip="192.0.2.2",
                peer_certificate=self.certificate("worker-0002"),
            )


if __name__ == "__main__":
    unittest.main()
