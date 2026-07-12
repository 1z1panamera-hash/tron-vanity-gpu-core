from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterator, Sequence


class WorkerState:
    """Minimal non-authoritative state persisted on the Vast worker."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO metadata(key, value) VALUES ('controller_revision', '-1');

                CREATE TABLE IF NOT EXISTS active_tasks (
                    item_id TEXT PRIMARY KEY,
                    class TEXT NOT NULL CHECK(class IN ('P0', 'P1', 'P2')),
                    pattern TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    search_shard TEXT,
                    search_cursor TEXT,
                    generation INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS result_outbox (
                    result_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    item_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    matched_address TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_worker_outbox_due
                    ON result_outbox(next_attempt_at);
                """
            )
        if self.path.exists():
            os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def revision(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='controller_revision'"
            ).fetchone()
            return int(row["value"])

    def apply_snapshot(
        self,
        revision: int,
        tasks: Sequence[dict[str, Any]],
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            keep = {str(task["item_id"]) for task in tasks}
            if keep:
                placeholders = ",".join("?" for _ in keep)
                connection.execute(
                    f"DELETE FROM active_tasks WHERE item_id NOT IN ({placeholders})",
                    tuple(keep),
                )
            else:
                connection.execute("DELETE FROM active_tasks")
            for task in tasks:
                connection.execute(
                    """
                    INSERT INTO active_tasks(
                        item_id, class, pattern, lease_id, search_shard,
                        search_cursor, generation, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        class=excluded.class,
                        pattern=excluded.pattern,
                        lease_id=excluded.lease_id,
                        search_shard=COALESCE(active_tasks.search_shard, excluded.search_shard),
                        search_cursor=COALESCE(active_tasks.search_cursor, excluded.search_cursor),
                        generation=excluded.generation,
                        updated_at=excluded.updated_at
                    """,
                    (
                        str(task["item_id"]),
                        str(task["class"]),
                        str(task["pattern"]),
                        str(task["lease_id"]),
                        task.get("search_shard"),
                        task.get("search_cursor"),
                        revision,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE metadata SET value=? WHERE key='controller_revision'", (str(revision),)
            )

    def active_tasks(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM active_tasks ORDER BY class, item_id"
            ).fetchall()
            return [dict(row) for row in rows]

    def update_checkpoint(
        self,
        item_id: str,
        search_shard: str,
        search_cursor: str,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            connection.execute(
                """
                UPDATE active_tasks SET search_shard=?, search_cursor=?, updated_at=?
                WHERE item_id=?
                """,
                (search_shard, search_cursor, now, item_id),
            )

    def enqueue_encrypted_result(
        self,
        *,
        result_id: str,
        event_id: str,
        item_id: str,
        lease_id: str,
        matched_address: str,
        encrypted_private_key: str,
        now: float | None = None,
    ) -> bool:
        if not encrypted_private_key.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
            raise ValueError("worker outbox accepts only armored Age ciphertext")
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO result_outbox(
                        result_id, event_id, item_id, lease_id, matched_address,
                        encrypted_private_key, attempts, next_attempt_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        result_id,
                        event_id,
                        item_id,
                        lease_id,
                        matched_address,
                        encrypted_private_key,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                existing = connection.execute(
                    """
                    SELECT result_id, event_id, item_id, lease_id, matched_address,
                           encrypted_private_key
                    FROM result_outbox WHERE result_id=? OR event_id=?
                    """,
                    (result_id, event_id),
                ).fetchone()
                if not existing or any(
                    (
                        existing["result_id"] != result_id,
                        existing["event_id"] != event_id,
                        existing["item_id"] != item_id,
                        existing["lease_id"] != lease_id,
                        existing["matched_address"] != matched_address,
                        existing["encrypted_private_key"] != encrypted_private_key,
                    )
                ):
                    raise ValueError("encrypted result conflicts with the durable outbox")
                return False
            return True

    def due_results(self, limit: int = 20, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM result_outbox
                WHERE next_attempt_at<=?
                ORDER BY created_at LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def acknowledge_result(self, result_id: str) -> None:
        with self._lock, self._transaction() as connection:
            connection.execute("DELETE FROM result_outbox WHERE result_id=?", (result_id,))

    def retry_result(
        self,
        result_id: str,
        error: str,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            row = connection.execute(
                "SELECT attempts FROM result_outbox WHERE result_id=?", (result_id,)
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            delay = min(30.0, 0.25 * (2 ** min(attempts, 7)))
            connection.execute(
                """
                UPDATE result_outbox SET attempts=?, next_attempt_at=?, last_error=?
                WHERE result_id=?
                """,
                (attempts, now + delay, error[:200], result_id),
            )
