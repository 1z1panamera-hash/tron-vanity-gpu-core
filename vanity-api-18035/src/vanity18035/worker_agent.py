from __future__ import annotations

import asyncio
import random
from typing import Any

from .core_adapter import CoreAdapter, CoreTask, EncryptedHit, UnixCoreAdapter
from .worker_client import ControllerClient, ControllerClientError
from .worker_config import WorkerSettings
from .worker_state import WorkerState


class WorkerAgent:
    def __init__(
        self,
        settings: WorkerSettings,
        state: WorkerState,
        client: ControllerClient,
        core: CoreAdapter,
    ):
        self.settings = settings
        self.state = state
        self.client = client
        self.core = core
        self._tasks: list[asyncio.Task[Any]] = []
        self._stopping = False

    async def run(self) -> None:
        self.settings.validate()
        self.state.initialize()
        await self.client.start()
        self._stopping = False
        self._tasks = [
            asyncio.create_task(self._control_loop(), name="vanity18035-worker-control"),
            asyncio.create_task(self._heartbeat_loop(), name="vanity18035-worker-heartbeat"),
            asyncio.create_task(self._hit_loop(), name="vanity18035-worker-hits"),
            asyncio.create_task(self._outbox_loop(), name="vanity18035-worker-outbox"),
        ]
        try:
            await asyncio.gather(*self._tasks)
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.core.close()
        await self.client.close()

    async def _control_loop(self) -> None:
        delay = self.settings.reconnect_min_seconds
        while not self._stopping:
            try:
                response = await self.client.post(
                    "/internal/v1/worker/control",
                    {
                        "since_revision": self.state.revision(),
                        "wait_seconds": 20,
                        "capabilities": {"gpu": "RTX 5090", "max_targets": 16},
                    },
                )
                revision = int(response["revision"])
                raw_tasks = response.get("tasks", [])
                if not isinstance(raw_tasks, list):
                    raise ControllerClientError("control tasks are not a list")
                self.state.apply_snapshot(revision, raw_tasks)
                tasks = [
                    CoreTask(
                        item_id=str(task["item_id"]),
                        task_class=str(task["class"]),
                        pattern=str(task["pattern"]),
                        lease_id=str(task["lease_id"]),
                        search_shard=str(task.get("search_shard") or ""),
                        search_cursor=str(task.get("search_cursor") or ""),
                    )
                    for task in raw_tasks
                ]
                await self.core.apply_snapshot(revision, tasks)
                delay = self.settings.reconnect_min_seconds
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(delay + random.random() * delay * 0.25)
                delay = min(self.settings.reconnect_max_seconds, delay * 2)

    async def _heartbeat_loop(self) -> None:
        while not self._stopping:
            try:
                progress = await self.core.progress()
                for update in progress:
                    self.state.update_checkpoint(
                        update["item_id"],
                        update.get("search_shard", ""),
                        update.get("search_cursor", ""),
                    )
                await self.client.post(
                    "/internal/v1/worker/heartbeat",
                    {
                        "status": "healthy" if self.core.is_healthy() else "unhealthy",
                        "error_code": None if self.core.is_healthy() else "CORE_DISCONNECTED",
                        "capabilities": {"gpu": "RTX 5090", "max_targets": 16},
                        "progress": progress,
                    },
                )
            except asyncio.CancelledError:
                return
            except Exception:
                pass
            await asyncio.sleep(self.settings.heartbeat_seconds)

    async def _hit_loop(self) -> None:
        while not self._stopping:
            try:
                hit = await self.core.next_hit()
            except asyncio.CancelledError:
                return
            except (ConnectionError, OSError):
                await asyncio.sleep(self.settings.reconnect_min_seconds)
                continue
            self.state.enqueue_encrypted_result(
                result_id=hit.result_id,
                event_id=hit.event_id,
                item_id=hit.item_id,
                lease_id=hit.lease_id,
                matched_address=hit.matched_address,
                encrypted_private_key=hit.encrypted_private_key,
            )
            await self.core.ack_hit(hit.result_id)

    async def _outbox_loop(self) -> None:
        while not self._stopping:
            rows = self.state.due_results()
            if not rows:
                await asyncio.sleep(0.1)
                continue
            for row in rows:
                try:
                    response = await self.client.post(
                        "/internal/v1/worker/result",
                        {
                            "event_id": row["event_id"],
                            "result_id": row["result_id"],
                            "item_id": row["item_id"],
                            "lease_id": row["lease_id"],
                            "matched_address": row["matched_address"],
                            "encrypted_private_key": row["encrypted_private_key"],
                        },
                    )
                    if response.get("ack") is True:
                        self.state.acknowledge_result(str(row["result_id"]))
                    else:
                        raise ControllerClientError("result was not acknowledged")
                except asyncio.CancelledError:
                    return
                except Exception as error:
                    self.state.retry_result(str(row["result_id"]), type(error).__name__)


async def main_async() -> None:
    settings = WorkerSettings.from_env()
    settings.validate()
    state = WorkerState(settings.state_db_path)
    client = ControllerClient(settings)
    core = UnixCoreAdapter(settings.core_socket_path)
    await WorkerAgent(settings, state, client, core).run()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
