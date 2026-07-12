#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import sqlite3
import stat
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


def message(message_type: int, body: bytes) -> bytes:
    payload = MAGIC + struct.pack(">BBH", VERSION, message_type, 0) + body
    return struct.pack(">I", len(payload)) + payload


def snapshot(revision: int, suffix: str) -> bytes:
    task = b"".join(
        text(value)
        for value in (
            "smoke-item-1",
            "P0",
            f"T*{suffix}",
            "smoke-lease-1",
            "",
            "",
        )
    )
    return message(SNAPSHOT, struct.pack(">QH", revision, 1) + task)


def hit_ack(result_id: str) -> bytes:
    return message(HIT_ACK, text(result_id))


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
    value = payload[offset : offset + length].decode("utf-8", errors="strict")
    return value, offset + length


def decode_hit(payload: bytes) -> dict[str, str] | None:
    if len(payload) < 8 or payload[:4] != MAGIC or payload[4] != VERSION:
        raise ValueError("invalid core frame header")
    if payload[5] == PROGRESS:
        return None
    if payload[5] != HIT or payload[6:8] != b"\x00\x00":
        raise ValueError("unexpected core frame type")
    offset = 8
    fields: dict[str, str] = {}
    for name, maximum in (
        ("result_id", 128),
        ("event_id", 128),
        ("item_id", 128),
        ("lease_id", 128),
        ("matched_address", 34),
        ("encrypted_private_key", 64 * 1024),
    ):
        fields[name], offset = read_text(payload, offset, maximum)
    if offset != len(payload):
        raise ValueError("trailing hit frame data")
    return fields


def connect(path: Path, timeout: float) -> socket.socket:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = path.stat()
            if not stat.S_ISSOCK(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
                raise PermissionError("core socket is not mode 0600")
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(str(path))
            return connection
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.05)
    raise TimeoutError("core socket did not become ready")


def verify_outbox(database_path: Path, hit: dict[str, str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with sqlite3.connect(database_path) as database:
            row = database.execute(
                """
                SELECT result_id,event_id,item_id,lease_id,matched_address,encrypted_private_key
                FROM result_outbox WHERE result_id=?
                """,
                (hit["result_id"],),
            ).fetchone()
        if row is not None:
            expected = tuple(
                hit[name]
                for name in (
                    "result_id",
                    "event_id",
                    "item_id",
                    "lease_id",
                    "matched_address",
                    "encrypted_private_key",
                )
            )
            if row != expected:
                raise AssertionError("durable outbox content differs from the socket hit")
            return
        time.sleep(0.02)
    raise TimeoutError("encrypted hit was not durable before notification")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--suffix", default="11111")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if len(args.suffix) != 5:
        raise SystemExit("smoke suffix must contain exactly five characters")

    started = time.monotonic()
    connection = connect(args.socket, 10.0)
    with connection:
        connection.sendall(snapshot(1, args.suffix))
        hit: dict[str, str] | None = None
        deadline = time.monotonic() + args.timeout
        while hit is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("P0 smoke task did not complete")
            hit = decode_hit(read_frame(connection, remaining))
        elapsed_ms = (time.monotonic() - started) * 1000.0
        address = hit["matched_address"]
        ciphertext = hit["encrypted_private_key"]
        if len(address) != 34 or not address.startswith("T") or not address.endswith(args.suffix):
            raise AssertionError("P0 result does not satisfy the requested suffix")
        if not ciphertext.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
            raise AssertionError("P0 result is not armored Age ciphertext")
        verify_outbox(args.database, hit, 1.0)
        connection.sendall(hit_ack(hit["result_id"]))
        readable, _, _ = select.select([connection], [], [], 1.5)
        if readable:
            duplicate = decode_hit(read_frame(connection, 0.5))
            if duplicate is not None and duplicate["result_id"] == hit["result_id"]:
                raise AssertionError("core resent a hit after durable ACK")

    print(
        json.dumps(
            {
                "address_matches": True,
                "age_armored": True,
                "durable_before_ack": True,
                "no_resend_after_ack": True,
                "elapsed_ms": round(elapsed_ms, 3),
                "socket_mode": oct(stat.S_IMODE(args.socket.stat().st_mode)),
                "database_mode": oct(stat.S_IMODE(args.database.stat().st_mode)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
