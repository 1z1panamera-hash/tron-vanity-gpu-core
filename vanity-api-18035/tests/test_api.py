from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from vanity18035.api import create_app

from .helpers import test_settings


def worker_metadata() -> dict[str, object]:
    return {
        "worker_id": "worker-0001",
        "event_id": str(uuid.uuid4()),
        "nonce": uuid.uuid4().hex,
        "timestamp": time.time(),
    }


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        settings = test_settings(Path(self.temp.name) / "controller.sqlite3")
        self.client = TestClient(TestServer(create_app(settings)))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.temp.cleanup()

    async def post_worker(self, path: str, payload: dict[str, object]):
        body = worker_metadata()
        body.update(payload)
        return await self.client.post(path, json=body)

    async def mark_worker_healthy(self, since_revision: int = -1) -> dict[str, object]:
        heartbeat = await self.post_worker(
            "/internal/v1/worker/heartbeat",
            {
                "status": "healthy",
                "capabilities": {"gpu": "test"},
                "progress": [],
            },
        )
        self.assertEqual(heartbeat.status, 200, await heartbeat.text())
        response = await self.post_worker(
            "/internal/v1/worker/control",
            {"since_revision": since_revision, "wait_seconds": 0, "capabilities": {"gpu": "test"}},
        )
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def test_control_long_poll_does_not_claim_worker_health(self) -> None:
        response = await self.post_worker(
            "/internal/v1/worker/control",
            {"since_revision": -1, "wait_seconds": 0, "capabilities": {"gpu": "test"}},
        )
        self.assertEqual(response.status, 200)
        find_response = await self.client.post("/v1/find", json={"suffix": "Yqvi2"})
        self.assertEqual(find_response.status, 503)

    async def test_p0_requires_a_healthy_worker(self) -> None:
        response = await self.client.post("/v1/find", json={"suffix": "Yqvi2"})
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())["error"], "GPU_UNAVAILABLE")

    async def test_p0_singleflight_result_and_cache(self) -> None:
        initial = await self.mark_worker_healthy()
        first_request = asyncio.create_task(
            self.client.post("/v1/find", json={"prefix": "", "suffix": "Yqvi2"})
        )
        second_request = asyncio.create_task(
            self.client.post("/v1/find", json={"prefix": "", "suffix": "Yqvi2"})
        )
        await asyncio.sleep(0.05)
        snapshot = await self.mark_worker_healthy(int(initial["revision"]))
        self.assertEqual(snapshot["class"], "P0")
        self.assertEqual(len(snapshot["tasks"]), 1)
        task = snapshot["tasks"][0]

        result_response = await self.post_worker(
            "/internal/v1/worker/result",
            {
                "result_id": str(uuid.uuid4()),
                "item_id": task["item_id"],
                "lease_id": task["lease_id"],
                "matched_address": "T" + "1" * 28 + "Yqvi2",
                "encrypted_private_key": "-----BEGIN AGE ENCRYPTED FILE-----\ntest-ciphertext\n",
            },
        )
        self.assertEqual(result_response.status, 200, await result_response.text())
        first = await first_request
        second = await second_request
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual((await first.json())["matched_address"], (await second.json())["matched_address"])

        replay = await self.client.post("/v1/find", json={"suffix": "Yqvi2"})
        self.assertEqual(replay.status, 200)
        self.assertTrue((await replay.json())["replayed"])

    async def test_background_class_separation(self) -> None:
        initial = await self.mark_worker_healthy()
        response = await self.client.post(
            "/v1/find",
            json={
                "items": [
                    {"prefix": "", "suffix": "ABCDEF"},
                    {"prefix": "LU", "suffix": "Yqvi2"},
                ]
            },
        )
        self.assertEqual(response.status, 200, await response.text())
        accepted = await response.json()
        self.assertEqual(len(accepted["items"]), 2)
        snapshot = await self.mark_worker_healthy(int(initial["revision"]))
        self.assertEqual(snapshot["class"], "P1")
        self.assertEqual({item["class"] for item in snapshot["tasks"]}, {"P1"})


if __name__ == "__main__":
    unittest.main()
