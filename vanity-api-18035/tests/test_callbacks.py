from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from vanity18035.callbacks import CallbackDispatcher
from vanity18035.database import ControllerDatabase
from vanity18035.patterns import classify_pattern

from .helpers import test_settings


class CallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_uses_fixed_url_and_marks_outbox_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = ControllerDatabase(Path(directory) / "controller.sqlite3")
            database.initialize()
            item, _ = database.create_item("customer-1", classify_pattern("LU", "Yqvi2"))
            leased = database.desired_tasks("worker-0001")["tasks"][0]
            event_id = str(uuid.uuid4())
            payload = {"event_id": event_id, "item_id": item["item_id"]}
            database.complete_item(
                worker_id="worker-0001",
                event_id=event_id,
                result_id=str(uuid.uuid4()),
                item_id=item["item_id"],
                lease_id=leased["lease_id"],
                matched_address="TLU" + "1" * 26 + "Yqvi2",
                encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\ntest\n",
                p0_cache_seconds=60,
                callback_payload=payload,
            )
            fixed_url = "https://customer.example/callback"
            delivered: list[tuple[str, dict[str, object]]] = []

            async def sender(url: str, body: dict[str, object]) -> bool:
                delivered.append((url, body))
                return True

            dispatcher = CallbackDispatcher(
                test_settings(database.path, callback_url=fixed_url),
                database,
                sender,
            )
            await dispatcher.start()
            try:
                for _ in range(100):
                    if delivered:
                        break
                    await asyncio.sleep(0.01)
            finally:
                await dispatcher.stop()
            self.assertEqual(delivered, [(fixed_url, payload)])
            self.assertEqual(database.due_callbacks(now=time.time() + 3600), [])

    async def test_failure_backs_off_without_recomputing_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = ControllerDatabase(Path(directory) / "controller.sqlite3")
            database.initialize()
            item, _ = database.create_item("customer-1", classify_pattern("LU", "Yqvi2"))
            leased = database.desired_tasks("worker-0001")["tasks"][0]
            event_id = str(uuid.uuid4())
            result_id = str(uuid.uuid4())
            database.complete_item(
                worker_id="worker-0001",
                event_id=event_id,
                result_id=result_id,
                item_id=item["item_id"],
                lease_id=leased["lease_id"],
                matched_address="TLU" + "1" * 26 + "Yqvi2",
                encrypted_private_key="-----BEGIN AGE ENCRYPTED FILE-----\ntest\n",
                p0_cache_seconds=60,
                callback_payload={"event_id": event_id},
                now=1000,
            )
            due = database.due_callbacks(now=1000)
            self.assertEqual(len(due), 1)
            database.finish_callback(event_id, False, "test failure", now=1000)
            self.assertEqual(database.due_callbacks(now=1001), [])
            self.assertEqual(len(database.due_callbacks(now=1002)), 1)
            self.assertEqual(database.get_item(item["item_id"])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
