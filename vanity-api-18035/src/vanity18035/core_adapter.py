from __future__ import annotations

import asyncio
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .core_protocol import (
    MAX_FRAME_SIZE,
    MessageType,
    decode_hit,
    decode_progress,
    encode_hit_ack,
    encode_snapshot,
    message_type,
)


@dataclass(frozen=True)
class CoreTask:
    item_id: str
    task_class: str
    pattern: str
    lease_id: str
    search_shard: str
    search_cursor: str


@dataclass(frozen=True)
class EncryptedHit:
    result_id: str
    event_id: str
    item_id: str
    lease_id: str
    matched_address: str
    encrypted_private_key: str


class CoreAdapter(Protocol):
    async def apply_snapshot(self, revision: int, tasks: Sequence[CoreTask]) -> None: ...

    async def next_hit(self) -> EncryptedHit: ...

    async def ack_hit(self, result_id: str) -> None: ...

    async def progress(self) -> list[dict[str, str]]: ...

    def is_healthy(self) -> bool: ...

    async def close(self) -> None: ...


class UnixCoreAdapter:
    """Non-secret Unix socket protocol to the long-running CUDA owner process.

    The core process performs private-key reconstruction and Age encryption. The
    Python agent receives only the matched public address and armored ciphertext.
    """

    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._hits: asyncio.Queue[EncryptedHit] = asyncio.Queue()
        self._progress: dict[str, dict[str, str]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        socket_stat = self.socket_path.stat()
        if not stat.S_ISSOCK(socket_stat.st_mode):
            raise ConnectionError("CUDA core path is not a Unix socket")
        if socket_stat.st_uid != os.geteuid() or stat.S_IMODE(socket_stat.st_mode) != 0o600:
            raise PermissionError("CUDA core socket must be owned by the worker and mode 0600")
        if (
            self._writer is not None
            and self._reader_task is not None
            and not self._reader_task.done()
        ):
            return
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            await asyncio.gather(
                asyncio.create_task(self._writer.wait_closed()),
                return_exceptions=True,
            )
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        self._reader = reader
        self._writer = writer
        self._reader_task = asyncio.create_task(self._read_loop(), name="vanity18035-core-reader")

    async def apply_snapshot(self, revision: int, tasks: Sequence[CoreTask]) -> None:
        if self._writer is None:
            await self.connect()
        await self._send(encode_snapshot(revision, tasks))
        active = {task.item_id for task in tasks}
        self._progress = {
            item_id: update
            for item_id, update in self._progress.items()
            if item_id in active
        }

    async def next_hit(self) -> EncryptedHit:
        if self._reader_task is None or self._reader_task.done():
            await self.connect()
        hit_task = asyncio.create_task(self._hits.get())
        assert self._reader_task is not None
        done, _ = await asyncio.wait(
            {hit_task, self._reader_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if hit_task in done:
            return hit_task.result()
        hit_task.cancel()
        await asyncio.gather(hit_task, return_exceptions=True)
        await self._reader_task
        raise ConnectionError("CUDA core socket closed")

    async def ack_hit(self, result_id: str) -> None:
        await self._send(encode_hit_ack(result_id))

    async def progress(self) -> list[dict[str, str]]:
        return list(self._progress.values())

    def is_healthy(self) -> bool:
        return (
            self._writer is not None
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            await asyncio.gather(
                asyncio.create_task(self._writer.wait_closed()),
                return_exceptions=True,
            )
            self._writer = None
        if self._reader_task:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
        self._reader = None

    async def _send(self, encoded: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("CUDA core socket is not connected")
        if len(encoded) > MAX_FRAME_SIZE:
            raise ValueError("core command exceeds the size limit")
        async with self._write_lock:
            try:
                self._writer.write(len(encoded).to_bytes(4, "big") + encoded)
                await self._writer.drain()
            except Exception:
                self._writer.close()
                self._writer = None
                raise

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                length = int.from_bytes(await self._reader.readexactly(4), "big")
                if length <= 0 or length > MAX_FRAME_SIZE:
                    raise ValueError("invalid CUDA core frame length")
                payload = await self._reader.readexactly(length)
                kind = message_type(payload)
                if kind == MessageType.HIT:
                    message = decode_hit(payload)
                    hit = EncryptedHit(
                        result_id=message.result_id,
                        event_id=message.event_id,
                        item_id=message.item_id,
                        lease_id=message.lease_id,
                        matched_address=message.matched_address,
                        encrypted_private_key=message.encrypted_private_key,
                    )
                    await self._hits.put(hit)
                elif kind == MessageType.PROGRESS:
                    message = decode_progress(payload)
                    item_id = message.item_id
                    self._progress[item_id] = {
                        "item_id": item_id,
                        "lease_id": message.lease_id,
                        "search_shard": message.search_shard,
                        "search_cursor": message.search_cursor,
                    }
                else:
                    raise ValueError("unknown CUDA core message type")
        except asyncio.CancelledError:
            return
        finally:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
            self._reader = None


class FakeCoreAdapter:
    def __init__(self):
        self.snapshots: list[tuple[int, Sequence[CoreTask]]] = []
        self.hits: asyncio.Queue[EncryptedHit] = asyncio.Queue()
        self.progress_rows: list[dict[str, str]] = []
        self.acked_hits: list[str] = []

    async def apply_snapshot(self, revision: int, tasks: Sequence[CoreTask]) -> None:
        self.snapshots.append((revision, list(tasks)))

    async def next_hit(self) -> EncryptedHit:
        return await self.hits.get()

    async def ack_hit(self, result_id: str) -> None:
        self.acked_hits.append(result_id)

    async def progress(self) -> list[dict[str, str]]:
        return list(self.progress_rows)

    def is_healthy(self) -> bool:
        return True

    async def close(self) -> None:
        return None
