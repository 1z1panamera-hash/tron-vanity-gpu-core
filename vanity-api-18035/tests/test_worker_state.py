from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from vanity18035.worker_state import WorkerState


class WorkerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.state = WorkerState(Path(self.temp.name) / "worker.sqlite3")
        self.state.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_snapshot_replaces_only_active_task_metadata(self) -> None:
        first = {
            "item_id": "item-0001",
            "class": "P1",
            "pattern": "TLU*Yqvi2",
            "lease_id": "lease-0001",
            "search_shard": "shard-a",
            "search_cursor": "100",
        }
        self.state.apply_snapshot(1, [first])
        self.state.update_checkpoint("item-0001", "shard-a", "200")
        refreshed = dict(first, lease_id="lease-0002", search_cursor="0")
        self.state.apply_snapshot(2, [refreshed])
        active = self.state.active_tasks()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["lease_id"], "lease-0002")
        self.assertEqual(active[0]["search_cursor"], "200")
        self.assertEqual(self.state.revision(), 2)

    def test_encrypted_outbox_is_durable_and_acknowledged(self) -> None:
        result_id = str(uuid.uuid4())
        inserted = self.state.enqueue_encrypted_result(
            result_id=result_id,
            event_id=str(uuid.uuid4()),
            item_id="item-0001",
            lease_id="lease-0001",
            matched_address="T" + "1" * 33,
            encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\nciphertext\n",
        )
        self.assertTrue(inserted)
        self.assertEqual(len(self.state.due_results()), 1)
        self.state.acknowledge_result(result_id)
        self.assertEqual(self.state.due_results(), [])

    def test_plaintext_result_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.state.enqueue_encrypted_result(
                result_id=str(uuid.uuid4()),
                event_id=str(uuid.uuid4()),
                item_id="item-0001",
                lease_id="lease-0001",
                matched_address="T" + "1" * 33,
                encrypted_private_key="not encrypted",
            )

    def test_conflicting_duplicate_result_is_rejected(self) -> None:
        result_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        ciphertext = "-----BEGIN AGE ENCRYPTED FILE-----\nciphertext\n"
        self.assertTrue(
            self.state.enqueue_encrypted_result(
                result_id=result_id,
                event_id=event_id,
                item_id="item-0001",
                lease_id="lease-0001",
                matched_address="T" + "1" * 33,
                encrypted_private_key=ciphertext,
            )
        )
        self.assertFalse(
            self.state.enqueue_encrypted_result(
                result_id=result_id,
                event_id=event_id,
                item_id="item-0001",
                lease_id="lease-0001",
                matched_address="T" + "1" * 33,
                encrypted_private_key=ciphertext,
            )
        )
        with self.assertRaises(ValueError):
            self.state.enqueue_encrypted_result(
                result_id=result_id,
                event_id=event_id,
                item_id="item-0001",
                lease_id="lease-0001",
                matched_address="T" + "2" * 33,
                encrypted_private_key=ciphertext,
            )


if __name__ == "__main__":
    unittest.main()
