from __future__ import annotations

import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path

from vanity18035.controller import Controller, P0TimeoutError
from vanity18035.database import ControllerDatabase
from vanity18035.patterns import classify_pattern

from .helpers import test_settings


AGE_CIPHERTEXT = (
    "-----BEGIN AGE ENCRYPTED FILE-----\n"
    "test-ciphertext\n"
    "-----END AGE ENCRYPTED FILE-----\n"
)


class ControllerAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.settings = test_settings(Path(self.temp.name) / "controller.sqlite3")
        self.database = ControllerDatabase(self.settings.db_path)
        self.controller = Controller(self.settings, self.database)
        await self.controller.start()
        self.database.record_worker("worker-0001", "healthy", {"gpu": "test"})

    async def asyncTearDown(self) -> None:
        await self.controller.stop()
        self.temp.cleanup()

    async def complete_p0(self, item: dict[str, object]) -> None:
        await self.controller.accept_result(
            worker_id="worker-0001",
            event_id=str(uuid.uuid4()),
            payload={
                "result_id": str(uuid.uuid4()),
                "item_id": item["item_id"],
                "lease_id": item["lease_id"],
                "matched_address": "T" + "1" * 28 + "Yqvi2",
                "encrypted_private_key": AGE_CIPHERTEXT,
            },
        )

    async def test_one_hundred_same_p0_requests_share_one_task(self) -> None:
        pattern = classify_pattern("", "Yqvi2")
        requests = [
            asyncio.create_task(self.controller.submit_p0(pattern))
            for _ in range(100)
        ]
        await asyncio.sleep(0)
        snapshot = self.database.desired_tasks("worker-0001")
        self.assertEqual(len(snapshot["tasks"]), 1)
        await self.complete_p0(snapshot["tasks"][0])
        results = await asyncio.gather(*requests)
        self.assertEqual(len({row["matched_address"] for row in results}), 1)

    async def test_disconnected_waiter_does_not_cancel_internal_p0(self) -> None:
        pattern = classify_pattern("", "Yqvi2")
        disconnected = asyncio.create_task(self.controller.submit_p0(pattern))
        await asyncio.sleep(0)
        first_snapshot = self.database.desired_tasks("worker-0001")
        first_item = first_snapshot["tasks"][0]
        disconnected.cancel()
        await asyncio.gather(disconnected, return_exceptions=True)

        retry = asyncio.create_task(self.controller.submit_p0(pattern))
        await asyncio.sleep(0)
        second_snapshot = self.database.desired_tasks("worker-0001")
        self.assertEqual(second_snapshot["tasks"][0]["item_id"], first_item["item_id"])
        await self.complete_p0(second_snapshot["tasks"][0])
        self.assertEqual((await retry)["matched_address"], "T" + "1" * 28 + "Yqvi2")

    async def test_hard_timeout_clears_singleflight_for_a_new_task(self) -> None:
        await self.controller.stop()
        self.settings = test_settings(
            self.settings.db_path,
            p0_hard_timeout_seconds=0.02,
            p0_http_timeout_seconds=0.5,
        )
        self.controller = Controller(self.settings, self.database)
        await self.controller.start()
        self.database.record_worker("worker-0001", "healthy", {"gpu": "test"})
        pattern = classify_pattern("", "Yqvi2")

        first = asyncio.create_task(self.controller.submit_p0(pattern))
        await asyncio.sleep(0)
        first_item = self.database.desired_tasks("worker-0001")["tasks"][0]["item_id"]
        with self.assertRaises(P0TimeoutError):
            await first

        second = asyncio.create_task(self.controller.submit_p0(pattern))
        await asyncio.sleep(0)
        second_item = self.database.desired_tasks("worker-0001")["tasks"][0]["item_id"]
        self.assertNotEqual(first_item, second_item)
        second.cancel()
        await asyncio.gather(second, return_exceptions=True)

    async def test_late_encrypted_result_after_timeout_is_terminally_acked(self) -> None:
        pattern = classify_pattern("", "Yqvi2")
        self.database.create_item("customer-1", pattern)
        task = self.database.desired_tasks("worker-0001")["tasks"][0]
        self.database.fail_item(task["item_id"], "P0_TIMEOUT")
        response = await self.controller.accept_result(
            worker_id="worker-0001",
            event_id=str(uuid.uuid4()),
            payload={
                "result_id": str(uuid.uuid4()),
                "item_id": task["item_id"],
                "lease_id": task["lease_id"],
                "matched_address": "T" + "1" * 28 + "Yqvi2",
                "encrypted_private_key": AGE_CIPHERTEXT,
            },
        )
        self.assertTrue(response["ack"])
        self.assertTrue(response["terminal"])
        self.assertFalse(response["accepted"])
        self.assertEqual(self.database.get_item(task["item_id"])["status"], "failed")


class BackgroundQueueAcceptanceTests(unittest.TestCase):
    def test_more_than_sixteen_background_targets_queue_and_refill(self) -> None:
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        patterns = [classify_pattern("", "A1111" + alphabet[index]) for index in range(24)]
        with tempfile.TemporaryDirectory() as directory:
            database = ControllerDatabase(Path(directory) / "controller.sqlite3")
            database.initialize()
            created = database.create_background_batch("customer-1", patterns)
            self.assertEqual(len(created["items"]), 24)

            first = database.desired_tasks("worker-0001")
            self.assertEqual(first["class"], "P2")
            self.assertEqual(len(first["tasks"]), 16)
            completed = first["tasks"][0]
            database.complete_item(
                worker_id="worker-0001",
                event_id=str(uuid.uuid4()),
                result_id=str(uuid.uuid4()),
                item_id=completed["item_id"],
                lease_id=completed["lease_id"],
                matched_address="T" + "1" * 27 + completed["suffix"],
                encrypted_private_key=AGE_CIPHERTEXT,
                p0_cache_seconds=60,
                callback_payload={"event_id": str(uuid.uuid4())},
            )
            second = database.desired_tasks("worker-0001")
            self.assertEqual(len(second["tasks"]), 16)
            self.assertNotIn(
                completed["item_id"],
                {task["item_id"] for task in second["tasks"]},
            )


if __name__ == "__main__":
    unittest.main()
