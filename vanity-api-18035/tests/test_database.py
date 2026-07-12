from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from vanity18035.database import ControllerDatabase, DatabaseError
from vanity18035.patterns import classify_pattern


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = ControllerDatabase(Path(self.temp.name) / "controller.sqlite3")
        self.database.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_active_pattern_is_deduplicated(self) -> None:
        pattern = classify_pattern("LU", "Yqvi2")
        first, created = self.database.create_item("customer-1", pattern)
        second, created_again = self.database.create_item("customer-1", pattern)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["item_id"], second["item_id"])

    def test_priority_is_p0_then_p1_then_p2(self) -> None:
        p2, _ = self.database.create_item("customer-1", classify_pattern("", "ABCDEF"))
        p1, _ = self.database.create_item("customer-1", classify_pattern("LU", "Yqvi2"))
        snapshot = self.database.desired_tasks("worker-0001")
        self.assertEqual(snapshot["class"], "P1")
        self.assertEqual([item["item_id"] for item in snapshot["tasks"]], [p1["item_id"]])

        p0, _ = self.database.create_item("customer-1", classify_pattern("", "Yqvi2"))
        snapshot = self.database.desired_tasks("worker-0001")
        self.assertEqual(snapshot["class"], "P0")
        self.assertEqual([item["item_id"] for item in snapshot["tasks"]], [p0["item_id"]])
        self.assertEqual(self.database.get_item(p2["item_id"])["status"], "queued")
        self.assertEqual(self.database.get_item(p1["item_id"])["status"], "paused")

    def test_result_is_idempotent_and_cached_for_p0(self) -> None:
        item, _ = self.database.create_item("customer-1", classify_pattern("", "Yqvi2"))
        snapshot = self.database.desired_tasks("worker-0001")
        leased = snapshot["tasks"][0]
        address = "T" + "1" * 28 + "Yqvi2"
        result_id = str(uuid.uuid4())
        args = dict(
            worker_id="worker-0001",
            event_id=str(uuid.uuid4()),
            result_id=result_id,
            item_id=item["item_id"],
            lease_id=leased["lease_id"],
            matched_address=address,
            encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\ntest\n",
            p0_cache_seconds=60,
            callback_payload=None,
        )
        result, created = self.database.complete_item(**args)
        replay, created_again = self.database.complete_item(**args)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(result["result_id"], replay["result_id"])
        self.assertEqual(
            self.database.get_p0_cache("customer-1", "Yqvi2")["matched_address"],
            address,
        )

    def test_nonce_replay_is_rejected(self) -> None:
        self.assertTrue(self.database.register_nonce("worker-0001", "a" * 32, 120))
        self.assertFalse(self.database.register_nonce("worker-0001", "a" * 32, 120))

    def test_conflicting_result_replay_is_rejected(self) -> None:
        item, _ = self.database.create_item("customer-1", classify_pattern("", "Yqvi2"))
        leased = self.database.desired_tasks("worker-0001")["tasks"][0]
        args = dict(
            worker_id="worker-0001",
            event_id=str(uuid.uuid4()),
            result_id=str(uuid.uuid4()),
            item_id=item["item_id"],
            lease_id=leased["lease_id"],
            matched_address="T" + "1" * 28 + "Yqvi2",
            encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\ntest\n",
            p0_cache_seconds=60,
            callback_payload=None,
        )
        self.database.complete_item(**args)
        args["matched_address"] = "T" + "2" * 28 + "Yqvi2"
        with self.assertRaises(DatabaseError):
            self.database.complete_item(**args)

    def test_callback_inflight_is_recovered_after_restart(self) -> None:
        item, _ = self.database.create_item("customer-1", classify_pattern("LU", "Yqvi2"))
        leased = self.database.desired_tasks("worker-0001")["tasks"][0]
        result_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        self.database.complete_item(
            worker_id="worker-0001",
            event_id=event_id,
            result_id=result_id,
            item_id=item["item_id"],
            lease_id=leased["lease_id"],
            matched_address="TLU" + "1" * 26 + "Yqvi2",
            encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\ntest\n",
            p0_cache_seconds=60,
            callback_payload={"event_id": event_id},
        )
        sending = self.database.due_callbacks(now=time.time() + 1)
        self.assertEqual([row["event_id"] for row in sending], [event_id])

        restarted = ControllerDatabase(self.database.path)
        restarted.initialize()
        recovered = restarted.due_callbacks(now=time.time() + 1)
        self.assertEqual([row["event_id"] for row in recovered], [event_id])


if __name__ == "__main__":
    unittest.main()
