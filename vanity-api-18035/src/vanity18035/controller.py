from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from .config import Settings
from .database import ControllerDatabase, DatabaseError
from .patterns import PatternSpec, TaskClass, address_matches


class P0BusyError(RuntimeError):
    pass


class GPUUnavailableError(RuntimeError):
    pass


class P0TimeoutError(TimeoutError):
    pass


class ResultValidationError(ValueError):
    pass


@dataclass
class P0Flight:
    item_id: str
    future: asyncio.Future[dict[str, Any]]


class Controller:
    def __init__(self, settings: Settings, database: ControllerDatabase):
        self.settings = settings
        self.database = database
        self.customer_id = "customer-1"
        self._p0_lock = asyncio.Lock()
        self._p0_flights: dict[str, P0Flight] = {}
        self._control_condition = asyncio.Condition()
        self._background_tasks: list[asyncio.Task[Any]] = []
        self._stopping = False

    async def start(self) -> None:
        self.database.initialize()
        self._stopping = False
        self._background_tasks = [
            asyncio.create_task(self._timeout_loop(), name="vanity18035-p0-timeouts"),
            asyncio.create_task(self._cleanup_loop(), name="vanity18035-cleanup"),
        ]

    async def stop(self) -> None:
        self._stopping = True
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def notify_control_change(self) -> None:
        async with self._control_condition:
            self._control_condition.notify_all()

    async def submit_p0(self, pattern: PatternSpec) -> dict[str, Any]:
        if pattern.task_class != TaskClass.P0:
            raise ValueError("submit_p0 requires a P0 pattern")
        cached = self.database.get_p0_cache(self.customer_id, pattern.suffix)
        if cached:
            return {
                "status": "completed",
                "matched_address": cached["matched_address"],
                "encrypted_private_key": cached["encrypted_private_key"],
                "elapsed_ms": 0,
                "replayed": True,
            }

        async with self._p0_lock:
            flight = self._p0_flights.get(pattern.suffix)
            if flight is None:
                active = self.database.get_active_pattern(self.customer_id, pattern.canonical)
                if active is None:
                    if not self.database.worker_is_healthy(self.settings.worker_stale_seconds):
                        raise GPUUnavailableError("GPU worker is not healthy")
                    if self.database.count_active_p0(self.customer_id) >= self.settings.p0_max_inflight:
                        raise P0BusyError("P0 concurrency limit reached")
                item, created = self.database.create_item(self.customer_id, pattern)
                future = asyncio.get_running_loop().create_future()
                flight = P0Flight(item_id=str(item["item_id"]), future=future)
                self._p0_flights[pattern.suffix] = flight
                if created:
                    await self.notify_control_change()

        try:
            return await asyncio.wait_for(
                asyncio.shield(flight.future),
                timeout=self.settings.p0_http_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise P0TimeoutError("P0 HTTP wait timed out") from error

    async def submit_background(self, patterns: Sequence[PatternSpec]) -> dict[str, Any]:
        result = self.database.create_background_batch(self.customer_id, patterns)
        if result["batch_id"] is not None:
            await self.notify_control_change()
        response_items = []
        for item in result["items"]:
            response_items.append(
                {
                    "batch_id": item["batch_id"],
                    "item_id": item["item_id"],
                    "class": item["class"],
                    "status": item["status"],
                    "deduplicated": bool(item.get("deduplicated", False)),
                }
            )
        return {"status": "queued", "batch_id": result["batch_id"], "items": response_items}

    async def wait_for_control_snapshot(
        self,
        worker_id: str,
        since_revision: int,
        wait_seconds: float,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + max(0.0, min(wait_seconds, 25.0))
        while True:
            async with self._control_condition:
                if self.database.revision() > since_revision:
                    break
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._control_condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
        return self.database.desired_tasks(worker_id)

    async def accept_result(
        self,
        *,
        worker_id: str,
        event_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        required = {
            "result_id",
            "item_id",
            "lease_id",
            "matched_address",
            "encrypted_private_key",
        }
        missing = required - set(payload)
        if missing:
            raise ResultValidationError(f"result is missing fields: {','.join(sorted(missing))}")
        item = self.database.get_item(str(payload["item_id"]))
        if item is None:
            raise ResultValidationError("result references an unknown item")

        pattern = PatternSpec(
            prefix=str(item["prefix"]),
            suffix=str(item["suffix"]),
            task_class=TaskClass(str(item["class"])),
            canonical=str(item["pattern"]),
        )
        matched_address = str(payload["matched_address"])
        encrypted_private_key = str(payload["encrypted_private_key"])
        if not address_matches(pattern, matched_address):
            raise ResultValidationError("matched address does not satisfy the assigned pattern")
        if not encrypted_private_key.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
            raise ResultValidationError("result is not an armored Age ciphertext")
        if len(encrypted_private_key.encode("utf-8")) > 64 * 1024:
            raise ResultValidationError("encrypted result exceeds the size limit")
        if item["status"] == "failed":
            return {
                "ack": True,
                "accepted": False,
                "terminal": True,
                "result_id": str(payload["result_id"]),
            }

        now = time.time()
        callback_payload = None
        if item["class"] != TaskClass.P0.value:
            callback_payload = {
                "event_id": event_id,
                "batch_id": item["batch_id"],
                "item_id": item["item_id"],
                "pattern": item["pattern"],
                "matched_address": matched_address,
                "encrypted_private_key": encrypted_private_key,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            }

        result, created = self.database.complete_item(
            worker_id=worker_id,
            event_id=event_id,
            result_id=str(payload["result_id"]),
            item_id=str(payload["item_id"]),
            lease_id=str(payload["lease_id"]),
            matched_address=matched_address,
            encrypted_private_key=encrypted_private_key,
            p0_cache_seconds=self.settings.p0_cache_seconds,
            callback_payload=callback_payload,
            now=now,
        )

        if item["class"] == TaskClass.P0.value:
            response = {
                "status": "completed",
                "matched_address": matched_address,
                "encrypted_private_key": encrypted_private_key,
                "elapsed_ms": max(0, int((now - float(item["created_at"])) * 1000)),
                "replayed": not created,
            }
            async with self._p0_lock:
                flight = self._p0_flights.pop(str(item["suffix"]), None)
                if flight and not flight.future.done():
                    flight.future.set_result(response)
        await self.notify_control_change()
        return {"ack": True, "created": created, "result_id": result["result_id"]}

    async def fail_p0(self, item_id: str, error_code: str) -> None:
        item = self.database.get_item(item_id)
        if not item or item["class"] != TaskClass.P0.value:
            return
        self.database.fail_item(item_id, error_code)
        async with self._p0_lock:
            flight = self._p0_flights.pop(str(item["suffix"]), None)
            if flight and not flight.future.done():
                flight.future.set_exception(P0TimeoutError(error_code))
        await self.notify_control_change()

    async def _timeout_loop(self) -> None:
        try:
            while not self._stopping:
                timed_out = self.database.timed_out_p0(self.settings.p0_hard_timeout_seconds)
                for item_id in timed_out:
                    item = self.database.get_item(item_id)
                    if not item:
                        continue
                    async with self._p0_lock:
                        flight = self._p0_flights.pop(str(item["suffix"]), None)
                        if flight and not flight.future.done():
                            flight.future.set_exception(P0TimeoutError("P0_TIMEOUT"))
                if timed_out:
                    await self.notify_control_change()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def _cleanup_loop(self) -> None:
        try:
            while not self._stopping:
                self.database.cleanup(self.settings.internal_clock_skew_seconds * 4)
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            return
