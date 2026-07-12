#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import select
import socket
import struct
import time
from pathlib import Path


MAGIC = b"V35C"
VERSION = 1
SNAPSHOT = 1
HIT = 2
PROGRESS = 3
HIT_ACK = 4
MAX_FRAME = 128 * 1024


def text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def frame(message_type: int, body: bytes) -> bytes:
    payload = MAGIC + struct.pack(">BBH", VERSION, message_type, 0) + body
    return struct.pack(">I", len(payload)) + payload


def snapshot(revision: int, item_id: str, task_class: str, pattern: str) -> bytes:
    lease_id = f"{item_id}-lease"
    task = b"".join(
        text(value)
        for value in (item_id, task_class, pattern, lease_id, "", "")
    )
    return frame(SNAPSHOT, struct.pack(">QH", revision, 1) + task)


def read_exact(connection: socket.socket, length: int, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("core frame timed out")
        readable, _, _ = select.select([connection], [], [], remaining)
        if not readable:
            raise TimeoutError("core frame timed out")
        chunk = connection.recv(length - len(result))
        if not chunk:
            raise ConnectionError("core socket closed")
        result.extend(chunk)
    return bytes(result)


def read_frame(connection: socket.socket, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    length = struct.unpack(">I", read_exact(connection, 4, deadline))[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError("invalid core frame length")
    return read_exact(connection, length, deadline)


def read_text(payload: bytes, offset: int, maximum: int) -> tuple[str, int]:
    if len(payload) - offset < 4:
        raise ValueError("truncated core text field")
    length = struct.unpack_from(">I", payload, offset)[0]
    offset += 4
    if length > maximum or len(payload) - offset < length:
        raise ValueError("invalid core text field")
    return payload[offset : offset + length].decode("utf-8"), offset + length


def hit_result_id(payload: bytes) -> str:
    result_id, _ = read_text(payload, 8, 128)
    return result_id


def progress(payload: bytes) -> tuple[str, int] | None:
    if len(payload) < 8 or payload[:4] != MAGIC or payload[4] != VERSION:
        raise ValueError("invalid core frame header")
    if payload[5] == HIT:
        return None
    if payload[5] != PROGRESS or payload[6:8] != b"\x00\x00":
        raise ValueError("unexpected core frame type")
    offset = 8
    item_id, offset = read_text(payload, offset, 128)
    _, offset = read_text(payload, offset, 128)
    _, offset = read_text(payload, offset, 256)
    cursor, offset = read_text(payload, offset, 256)
    if offset != len(payload) or not cursor.isdigit():
        raise ValueError("invalid progress frame")
    return item_id, int(cursor)


def wait_for_progress(
    connection: socket.socket, expected_item: str, timeout: float
) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = read_frame(connection, deadline - time.monotonic())
        decoded = progress(payload)
        if decoded is None:
            connection.sendall(frame(HIT_ACK, text(hit_result_id(payload))))
            continue
        item_id, cursor = decoded
        if item_id == expected_item:
            return cursor
    raise TimeoutError(f"no progress for {expected_item}")


def connect(path: Path, timeout: float) -> socket.socket:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(str(path))
            return connection
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.05)
    raise TimeoutError("core socket did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    args = parser.parse_args()

    with connect(args.socket, 10.0) as connection:
        connection.sendall(snapshot(1, "scheduler-p2", "P2", "T*11111111"))
        p2_before = wait_for_progress(connection, "scheduler-p2", 4.0)

        connection.sendall(snapshot(2, "scheduler-p1", "P1", "TLU*11111"))
        p1_cursor = wait_for_progress(connection, "scheduler-p1", 4.0)

        connection.sendall(snapshot(3, "scheduler-p2", "P2", "T*11111111"))
        p2_after = wait_for_progress(connection, "scheduler-p2", 4.0)

    if p2_after <= p2_before:
        raise AssertionError("P2 cursor reset after a class switch")
    print(
        json.dumps(
            {
                "p1_progressed": p1_cursor > 0,
                "p2_cursor_before": p2_before,
                "p2_cursor_after": p2_after,
                "p2_cursor_preserved": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
