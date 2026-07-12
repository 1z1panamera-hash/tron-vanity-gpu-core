from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from vanity18035.core_adapter import EncryptedHit, FakeCoreAdapter
from vanity18035.worker_agent import WorkerAgent
from vanity18035.worker_state import WorkerState

from .test_worker_config import settings


class UnusedClient:
    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


class WorkerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_hit_is_durable_before_core_ack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker_settings = settings(directory)
            state = WorkerState(Path(directory) / "worker.sqlite3")
            state.initialize()
            core = FakeCoreAdapter()
            agent = WorkerAgent(worker_settings, state, UnusedClient(), core)  # type: ignore[arg-type]
            loop = asyncio.create_task(agent._hit_loop())
            hit = EncryptedHit(
                result_id="result-1",
                event_id="event-1",
                item_id="item-1",
                lease_id="lease-1",
                matched_address="T" + "1" * 28 + "Yqvi2",
                encrypted_private_key=(
                    "-----BEGIN AGE ENCRYPTED FILE-----\ntest\n"
                    "-----END AGE ENCRYPTED FILE-----\n"
                ),
            )
            await core.hits.put(hit)
            for _ in range(100):
                if core.acked_hits:
                    break
                await asyncio.sleep(0.001)
            self.assertEqual(core.acked_hits, ["result-1"])
            rows = state.due_results()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["result_id"], "result-1")
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
