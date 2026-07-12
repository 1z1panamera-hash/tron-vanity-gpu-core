from __future__ import annotations

import dataclasses
import enum
import struct
from collections.abc import Sequence


MAGIC = b"V35C"
VERSION = 1
MAX_FRAME_SIZE = 128 * 1024
MAX_TASKS = 16


class MessageType(enum.IntEnum):
    SNAPSHOT = 1
    HIT = 2
    PROGRESS = 3
    HIT_ACK = 4


@dataclasses.dataclass(frozen=True)
class DecodedHit:
    result_id: str
    event_id: str
    item_id: str
    lease_id: str
    matched_address: str
    encrypted_private_key: str


@dataclasses.dataclass(frozen=True)
class DecodedProgress:
    item_id: str
    lease_id: str
    search_shard: str
    search_cursor: str


class ProtocolError(ValueError):
    pass


class _Writer:
    def __init__(self, message_type: MessageType):
        self.data = bytearray(MAGIC)
        self.data.extend(struct.pack(">BBH", VERSION, int(message_type), 0))

    def u16(self, value: int) -> None:
        self.data.extend(struct.pack(">H", value))

    def u64(self, value: int) -> None:
        self.data.extend(struct.pack(">Q", value))

    def text(self, value: str, maximum: int, field: str, *, allow_empty: bool = True) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > maximum:
            raise ProtocolError(f"{field} exceeds the protocol limit")
        if not allow_empty and not encoded:
            raise ProtocolError(f"{field} cannot be empty")
        self.data.extend(struct.pack(">I", len(encoded)))
        self.data.extend(encoded)

    def finish(self) -> bytes:
        if len(self.data) > MAX_FRAME_SIZE:
            raise ProtocolError("core frame exceeds the size limit")
        return bytes(self.data)


class _Reader:
    def __init__(self, payload: bytes, expected: MessageType):
        if not 8 <= len(payload) <= MAX_FRAME_SIZE:
            raise ProtocolError("invalid core frame size")
        if payload[:4] != MAGIC:
            raise ProtocolError("invalid core protocol magic")
        version, raw_type, reserved = struct.unpack_from(">BBH", payload, 4)
        if version != VERSION:
            raise ProtocolError("unsupported core protocol version")
        if raw_type != int(expected):
            raise ProtocolError("unexpected core message type")
        if reserved != 0:
            raise ProtocolError("core protocol reserved bits are nonzero")
        self.payload = payload
        self.offset = 8

    def _take(self, length: int) -> bytes:
        if length < 0 or length > len(self.payload) - self.offset:
            raise ProtocolError("truncated core frame")
        value = self.payload[self.offset : self.offset + length]
        self.offset += length
        return value

    def text(self, maximum: int, field: str, *, allow_empty: bool = True) -> str:
        length = struct.unpack(">I", self._take(4))[0]
        if length > maximum:
            raise ProtocolError(f"{field} exceeds the protocol limit")
        if not allow_empty and length == 0:
            raise ProtocolError(f"{field} cannot be empty")
        try:
            return self._take(length).decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ProtocolError(f"{field} is not valid UTF-8") from error

    def finish(self) -> None:
        if self.offset != len(self.payload):
            raise ProtocolError("trailing core protocol data")


def message_type(payload: bytes) -> MessageType:
    if not 8 <= len(payload) <= MAX_FRAME_SIZE or payload[:4] != MAGIC:
        raise ProtocolError("invalid core frame header")
    if payload[4] != VERSION:
        raise ProtocolError("unsupported core protocol version")
    try:
        return MessageType(payload[5])
    except ValueError as error:
        raise ProtocolError("unknown core message type") from error


def encode_snapshot(revision: int, tasks: Sequence[object]) -> bytes:
    if not 0 <= revision < 2**64:
        raise ProtocolError("revision is outside uint64 range")
    if len(tasks) > MAX_TASKS:
        raise ProtocolError("snapshot has too many tasks")
    writer = _Writer(MessageType.SNAPSHOT)
    writer.u64(revision)
    writer.u16(len(tasks))
    for task in tasks:
        values = dataclasses.asdict(task) if dataclasses.is_dataclass(task) else dict(task)  # type: ignore[arg-type]
        task_class = str(values["task_class"])
        if task_class not in {"P0", "P1", "P2"}:
            raise ProtocolError("invalid task class")
        writer.text(str(values["item_id"]), 128, "item_id", allow_empty=False)
        writer.text(task_class, 2, "task_class", allow_empty=False)
        writer.text(str(values["pattern"]), 64, "pattern", allow_empty=False)
        writer.text(str(values["lease_id"]), 128, "lease_id", allow_empty=False)
        writer.text(str(values.get("search_shard", "")), 256, "search_shard")
        writer.text(str(values.get("search_cursor", "")), 256, "search_cursor")
    return writer.finish()


def encode_hit(hit: DecodedHit) -> bytes:
    if len(hit.matched_address) != 34 or not hit.matched_address.startswith("T"):
        raise ProtocolError("invalid TRON address")
    if not hit.encrypted_private_key.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
        raise ProtocolError("hit is not armored Age ciphertext")
    writer = _Writer(MessageType.HIT)
    writer.text(hit.result_id, 128, "result_id", allow_empty=False)
    writer.text(hit.event_id, 128, "event_id", allow_empty=False)
    writer.text(hit.item_id, 128, "item_id", allow_empty=False)
    writer.text(hit.lease_id, 128, "lease_id", allow_empty=False)
    writer.text(hit.matched_address, 34, "matched_address", allow_empty=False)
    writer.text(hit.encrypted_private_key, 64 * 1024, "encrypted_private_key", allow_empty=False)
    return writer.finish()


def decode_hit(payload: bytes) -> DecodedHit:
    reader = _Reader(payload, MessageType.HIT)
    hit = DecodedHit(
        result_id=reader.text(128, "result_id", allow_empty=False),
        event_id=reader.text(128, "event_id", allow_empty=False),
        item_id=reader.text(128, "item_id", allow_empty=False),
        lease_id=reader.text(128, "lease_id", allow_empty=False),
        matched_address=reader.text(34, "matched_address", allow_empty=False),
        encrypted_private_key=reader.text(
            64 * 1024, "encrypted_private_key", allow_empty=False
        ),
    )
    reader.finish()
    if len(hit.matched_address) != 34 or not hit.matched_address.startswith("T"):
        raise ProtocolError("invalid TRON address")
    if not hit.encrypted_private_key.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
        raise ProtocolError("hit is not armored Age ciphertext")
    return hit


def encode_progress(progress: DecodedProgress) -> bytes:
    writer = _Writer(MessageType.PROGRESS)
    writer.text(progress.item_id, 128, "item_id", allow_empty=False)
    writer.text(progress.lease_id, 128, "lease_id", allow_empty=False)
    writer.text(progress.search_shard, 256, "search_shard")
    writer.text(progress.search_cursor, 256, "search_cursor")
    return writer.finish()


def decode_progress(payload: bytes) -> DecodedProgress:
    reader = _Reader(payload, MessageType.PROGRESS)
    progress = DecodedProgress(
        item_id=reader.text(128, "item_id", allow_empty=False),
        lease_id=reader.text(128, "lease_id", allow_empty=False),
        search_shard=reader.text(256, "search_shard"),
        search_cursor=reader.text(256, "search_cursor"),
    )
    reader.finish()
    return progress


def encode_hit_ack(result_id: str) -> bytes:
    writer = _Writer(MessageType.HIT_ACK)
    writer.text(result_id, 128, "result_id", allow_empty=False)
    return writer.finish()
