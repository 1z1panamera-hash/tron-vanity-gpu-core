from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .patterns import PatternSpec, TaskClass


ACTIVE_STATUSES = ("queued", "active", "paused")


class DatabaseError(RuntimeError):
    """Raised when persistent task state violates an invariant."""


class ControllerDatabase:
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
                INSERT OR IGNORE INTO metadata(key, value) VALUES ('control_revision', '0');

                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    completed_at REAL
                );

                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                    customer_id TEXT NOT NULL,
                    class TEXT NOT NULL CHECK(class IN ('P0', 'P1', 'P2')),
                    prefix TEXT NOT NULL,
                    suffix TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'active', 'paused', 'completed', 'failed')),
                    search_shard TEXT,
                    search_cursor TEXT,
                    lease_id TEXT,
                    lease_worker_id TEXT,
                    lease_expires_at REAL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    error_code TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_items_priority
                    ON items(class, status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_items_active_pattern
                    ON items(customer_id, pattern)
                    WHERE status IN ('queued', 'active', 'paused');

                CREATE TABLE IF NOT EXISTS results (
                    result_id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL UNIQUE REFERENCES items(item_id),
                    matched_address TEXT NOT NULL UNIQUE,
                    encrypted_private_key TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS p0_cache (
                    customer_id TEXT NOT NULL,
                    suffix TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    result_id TEXT NOT NULL,
                    matched_address TEXT NOT NULL,
                    encrypted_private_key TEXT NOT NULL,
                    completed_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY(customer_id, suffix)
                );

                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    last_seen_at REAL NOT NULL,
                    last_error_code TEXT
                );

                CREATE TABLE IF NOT EXISTS request_nonces (
                    worker_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    seen_at REAL NOT NULL,
                    PRIMARY KEY(worker_id, nonce)
                );

                CREATE TABLE IF NOT EXISTS callback_outbox (
                    event_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL UNIQUE REFERENCES results(result_id),
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'sending', 'delivered', 'failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    delivered_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_callback_due
                    ON callback_outbox(status, next_attempt_at);
                """
            )
            connection.execute(
                """
                UPDATE callback_outbox SET
                    status='failed',
                    next_attempt_at=?,
                    last_error='dispatcher_restarted'
                WHERE status='sending'
                """,
                (time.time(),),
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

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _bump_revision(connection: sqlite3.Connection) -> int:
        connection.execute(
            "UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='control_revision'"
        )
        row = connection.execute(
            "SELECT CAST(value AS INTEGER) AS revision FROM metadata WHERE key='control_revision'"
        ).fetchone()
        return int(row["revision"])

    def revision(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT CAST(value AS INTEGER) AS revision FROM metadata WHERE key='control_revision'"
            ).fetchone()
            return int(row["revision"])

    def get_active_pattern(self, customer_id: str, pattern: str) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM items
                WHERE customer_id=? AND pattern=? AND status IN ({placeholders})
                ORDER BY created_at LIMIT 1
                """,
                (customer_id, pattern, *ACTIVE_STATUSES),
            ).fetchone()
            return dict(row) if row else None

    def create_item(
        self,
        customer_id: str,
        pattern: PatternSpec,
        now: float | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
            existing = connection.execute(
                f"""
                SELECT * FROM items
                WHERE customer_id=? AND pattern=? AND status IN ({placeholders})
                ORDER BY created_at LIMIT 1
                """,
                (customer_id, pattern.canonical, *ACTIVE_STATUSES),
            ).fetchone()
            if existing:
                return dict(existing), False

            batch_id = self._uuid()
            item_id = self._uuid()
            connection.execute(
                """
                INSERT INTO batches(
                    batch_id, customer_id, status, total_items, completed_items, created_at
                ) VALUES (?, ?, 'queued', 1, 0, ?)
                """,
                (batch_id, customer_id, now),
            )
            connection.execute(
                """
                INSERT INTO items(
                    item_id, batch_id, customer_id, class, prefix, suffix, pattern,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    item_id,
                    batch_id,
                    customer_id,
                    pattern.task_class.value,
                    pattern.prefix,
                    pattern.suffix,
                    pattern.canonical,
                    now,
                ),
            )
            self._bump_revision(connection)
            row = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            return dict(row), True

    def create_background_batch(
        self,
        customer_id: str,
        patterns: Sequence[PatternSpec],
        now: float | None = None,
    ) -> dict[str, Any]:
        if not patterns:
            raise DatabaseError("background batch cannot be empty")
        if any(pattern.task_class == TaskClass.P0 for pattern in patterns):
            raise DatabaseError("P0 cannot be submitted in a background batch")
        now = time.time() if now is None else now
        unique: dict[str, PatternSpec] = {}
        for pattern in patterns:
            unique.setdefault(pattern.canonical, pattern)

        response_items: list[dict[str, Any]] = []
        new_items: list[tuple[str, PatternSpec]] = []
        with self._lock, self._transaction() as connection:
            placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
            for pattern in unique.values():
                existing = connection.execute(
                    f"""
                    SELECT * FROM items
                    WHERE customer_id=? AND pattern=? AND status IN ({placeholders})
                    ORDER BY created_at LIMIT 1
                    """,
                    (customer_id, pattern.canonical, *ACTIVE_STATUSES),
                ).fetchone()
                if existing:
                    item = dict(existing)
                    item["deduplicated"] = True
                    response_items.append(item)
                else:
                    new_items.append((self._uuid(), pattern))

            batch_id: str | None = None
            if new_items:
                batch_id = self._uuid()
                connection.execute(
                    """
                    INSERT INTO batches(
                        batch_id, customer_id, status, total_items, completed_items, created_at
                    ) VALUES (?, ?, 'queued', ?, 0, ?)
                    """,
                    (batch_id, customer_id, len(new_items), now),
                )
                for item_id, pattern in new_items:
                    connection.execute(
                        """
                        INSERT INTO items(
                            item_id, batch_id, customer_id, class, prefix, suffix, pattern,
                            status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                        """,
                        (
                            item_id,
                            batch_id,
                            customer_id,
                            pattern.task_class.value,
                            pattern.prefix,
                            pattern.suffix,
                            pattern.canonical,
                            now,
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM items WHERE item_id=?", (item_id,)
                    ).fetchone()
                    item = dict(row)
                    item["deduplicated"] = False
                    response_items.append(item)
                self._bump_revision(connection)

            return {"batch_id": batch_id, "items": response_items}

    def count_active_p0(self, customer_id: str) -> int:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS count FROM items
                WHERE customer_id=? AND class='P0' AND status IN ({placeholders})
                """,
                (customer_id, *ACTIVE_STATUSES),
            ).fetchone()
            return int(row["count"])

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            return dict(row) if row else None

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            batch = connection.execute(
                "SELECT * FROM batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if not batch:
                return None
            items = connection.execute(
                """
                SELECT item_id, class, prefix, suffix, pattern, status, created_at,
                       started_at, completed_at, error_code
                FROM items WHERE batch_id=? ORDER BY created_at, item_id
                """,
                (batch_id,),
            ).fetchall()
            result = dict(batch)
            result["items"] = [dict(row) for row in items]
            return result

    def get_p0_cache(
        self,
        customer_id: str,
        suffix: str,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        now = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM p0_cache
                WHERE customer_id=? AND suffix=? AND expires_at>?
                """,
                (customer_id, suffix, now),
            ).fetchone()
            return dict(row) if row else None

    def record_worker(
        self,
        worker_id: str,
        status: str,
        capabilities: dict[str, Any],
        error_code: str | None = None,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO workers(worker_id, status, capabilities_json, last_seen_at, last_error_code)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    status=excluded.status,
                    capabilities_json=excluded.capabilities_json,
                    last_seen_at=excluded.last_seen_at,
                    last_error_code=excluded.last_error_code
                """,
                (worker_id, status, json.dumps(capabilities, sort_keys=True), now, error_code),
            )

    def worker_is_healthy(self, stale_seconds: float, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM workers
                WHERE status='healthy' AND last_seen_at>=?
                LIMIT 1
                """,
                (now - stale_seconds,),
            ).fetchone()
            return row is not None

    def register_nonce(
        self,
        worker_id: str,
        nonce: str,
        retention_seconds: float,
        now: float | None = None,
    ) -> bool:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            connection.execute(
                "DELETE FROM request_nonces WHERE seen_at<?", (now - retention_seconds,)
            )
            try:
                connection.execute(
                    "INSERT INTO request_nonces(worker_id, nonce, seen_at) VALUES (?, ?, ?)",
                    (worker_id, nonce, now),
                )
            except sqlite3.IntegrityError:
                return False
            return True

    def desired_tasks(
        self,
        worker_id: str,
        lease_seconds: float = 5.0,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            active_p0 = connection.execute(
                """
                SELECT * FROM items
                WHERE class='P0' AND status IN ('queued', 'active')
                ORDER BY created_at LIMIT 8
                """
            ).fetchall()
            selected_class: str | None
            selected: Sequence[sqlite3.Row]
            if active_p0:
                selected_class = "P0"
                selected = active_p0
            else:
                p1 = connection.execute(
                    """
                    SELECT * FROM items
                    WHERE class='P1' AND status IN ('queued', 'active', 'paused')
                    ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at
                    LIMIT 16
                    """
                ).fetchall()
                if p1:
                    selected_class = "P1"
                    selected = p1
                else:
                    selected_class = "P2"
                    selected = connection.execute(
                        """
                        SELECT * FROM items
                        WHERE class='P2' AND status IN ('queued', 'active', 'paused')
                        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at
                        LIMIT 16
                        """
                    ).fetchall()

            selected_ids = {str(row["item_id"]) for row in selected}
            changed = False
            for task_class in ("P0", "P1", "P2"):
                rows = connection.execute(
                    """
                    SELECT item_id, status FROM items
                    WHERE class=? AND status IN ('queued', 'active', 'paused')
                    """,
                    (task_class,),
                ).fetchall()
                for row in rows:
                    item_id = str(row["item_id"])
                    wanted = "active" if item_id in selected_ids else (
                        "paused" if row["status"] == "active" else row["status"]
                    )
                    if wanted != row["status"]:
                        connection.execute(
                            "UPDATE items SET status=? WHERE item_id=?", (wanted, item_id)
                        )
                        changed = True

            payload_tasks: list[dict[str, Any]] = []
            for row in selected:
                item_id = str(row["item_id"])
                lease_id = row["lease_id"]
                if (
                    not lease_id
                    or row["lease_worker_id"] != worker_id
                    or not row["lease_expires_at"]
                    or float(row["lease_expires_at"]) <= now
                ):
                    lease_id = self._uuid()
                connection.execute(
                    """
                    UPDATE items SET
                        status='active',
                        started_at=COALESCE(started_at, ?),
                        lease_id=?,
                        lease_worker_id=?,
                        lease_expires_at=?
                    WHERE item_id=?
                    """,
                    (now, lease_id, worker_id, now + lease_seconds, item_id),
                )
                item = dict(row)
                item.update(
                    {
                        "status": "active",
                        "lease_id": lease_id,
                        "lease_worker_id": worker_id,
                        "lease_expires_at": now + lease_seconds,
                    }
                )
                payload_tasks.append(item)

            revision = self._bump_revision(connection) if changed else int(
                connection.execute(
                    "SELECT value FROM metadata WHERE key='control_revision'"
                ).fetchone()["value"]
            )
            return {"revision": revision, "class": selected_class if selected else None, "tasks": payload_tasks}

    def update_progress(
        self,
        worker_id: str,
        updates: Iterable[dict[str, Any]],
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            for update in updates:
                connection.execute(
                    """
                    UPDATE items SET search_shard=?, search_cursor=?, lease_expires_at=?
                    WHERE item_id=? AND lease_id=? AND lease_worker_id=? AND status='active'
                    """,
                    (
                        str(update.get("search_shard", "")),
                        str(update.get("search_cursor", "")),
                        now + 5.0,
                        str(update["item_id"]),
                        str(update["lease_id"]),
                        worker_id,
                    ),
                )

    def complete_item(
        self,
        *,
        worker_id: str,
        event_id: str,
        result_id: str,
        item_id: str,
        lease_id: str,
        matched_address: str,
        encrypted_private_key: str,
        p0_cache_seconds: float,
        callback_payload: dict[str, Any] | None,
        now: float | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM results WHERE result_id=?", (result_id,)
            ).fetchone()
            if existing:
                if (
                    existing["item_id"] != item_id
                    or existing["matched_address"] != matched_address
                    or existing["encrypted_private_key"] != encrypted_private_key
                ):
                    raise DatabaseError("result ID conflicts with the stored result")
                return dict(existing), False

            item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            if not item:
                raise DatabaseError("result references an unknown item")
            if item["status"] == "completed":
                existing = connection.execute(
                    "SELECT * FROM results WHERE item_id=?", (item_id,)
                ).fetchone()
                if existing:
                    if (
                        existing["matched_address"] != matched_address
                        or existing["encrypted_private_key"] != encrypted_private_key
                    ):
                        raise DatabaseError("completed item conflicts with the submitted result")
                    return dict(existing), False
                raise DatabaseError("completed item has no result")
            if item["lease_id"] != lease_id or item["lease_worker_id"] != worker_id:
                raise DatabaseError("result lease does not match the active worker lease")

            try:
                connection.execute(
                    """
                    INSERT INTO results(
                        result_id, item_id, matched_address, encrypted_private_key, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (result_id, item_id, matched_address, encrypted_private_key, now),
                )
            except sqlite3.IntegrityError as error:
                raise DatabaseError("result address or item is not unique") from error

            connection.execute(
                """
                UPDATE items SET status='completed', completed_at=?, error_code=NULL
                WHERE item_id=?
                """,
                (now, item_id),
            )
            connection.execute(
                """
                UPDATE batches SET
                    completed_items=completed_items+1,
                    status=CASE WHEN completed_items+1>=total_items THEN 'completed' ELSE status END,
                    completed_at=CASE WHEN completed_items+1>=total_items THEN ? ELSE completed_at END
                WHERE batch_id=?
                """,
                (now, item["batch_id"]),
            )

            if item["class"] == "P0":
                connection.execute(
                    """
                    INSERT INTO p0_cache(
                        customer_id, suffix, item_id, result_id, matched_address,
                        encrypted_private_key, completed_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(customer_id, suffix) DO UPDATE SET
                        item_id=excluded.item_id,
                        result_id=excluded.result_id,
                        matched_address=excluded.matched_address,
                        encrypted_private_key=excluded.encrypted_private_key,
                        completed_at=excluded.completed_at,
                        expires_at=excluded.expires_at
                    """,
                    (
                        item["customer_id"],
                        item["suffix"],
                        item_id,
                        result_id,
                        matched_address,
                        encrypted_private_key,
                        now,
                        now + p0_cache_seconds,
                    ),
                )
            elif callback_payload is not None:
                connection.execute(
                    """
                    INSERT INTO callback_outbox(
                        event_id, result_id, payload_json, status, attempts,
                        next_attempt_at, created_at
                    ) VALUES (?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (event_id, result_id, json.dumps(callback_payload, sort_keys=True), now, now),
                )

            self._bump_revision(connection)
            result = connection.execute(
                "SELECT * FROM results WHERE result_id=?", (result_id,)
            ).fetchone()
            return dict(result), True

    def fail_item(self, item_id: str, error_code: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            if not item or item["status"] in ("completed", "failed"):
                return
            connection.execute(
                """
                UPDATE items SET status='failed', completed_at=?, error_code=?
                WHERE item_id=?
                """,
                (now, error_code, item_id),
            )
            connection.execute(
                "UPDATE batches SET status='failed', completed_at=? WHERE batch_id=?",
                (now, item["batch_id"]),
            )
            self._bump_revision(connection)

    def timed_out_p0(self, hard_timeout: float, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT item_id, batch_id FROM items
                WHERE class='P0' AND status='active' AND started_at IS NOT NULL
                  AND started_at<=?
                """,
                (now - hard_timeout,),
            ).fetchall()
            item_ids = [str(row["item_id"]) for row in rows]
            for row in rows:
                connection.execute(
                    """
                    UPDATE items SET status='failed', completed_at=?, error_code='P0_TIMEOUT'
                    WHERE item_id=?
                    """,
                    (now, row["item_id"]),
                )
                connection.execute(
                    "UPDATE batches SET status='failed', completed_at=? WHERE batch_id=?",
                    (now, row["batch_id"]),
                )
            if item_ids:
                self._bump_revision(connection)
            return item_ids

    def due_callbacks(self, limit: int = 20, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM callback_outbox
                WHERE status IN ('pending', 'failed') AND next_attempt_at<=?
                ORDER BY next_attempt_at LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            event_ids = [str(row["event_id"]) for row in rows]
            if event_ids:
                connection.executemany(
                    "UPDATE callback_outbox SET status='sending' WHERE event_id=?",
                    [(event_id,) for event_id in event_ids],
                )
            return [dict(row) for row in rows]

    def finish_callback(
        self,
        event_id: str,
        delivered: bool,
        error: str | None = None,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            row = connection.execute(
                "SELECT attempts FROM callback_outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            if delivered:
                connection.execute(
                    """
                    UPDATE callback_outbox SET
                        status='delivered', attempts=?, delivered_at=?, last_error=NULL
                    WHERE event_id=?
                    """,
                    (attempts, now, event_id),
                )
            else:
                delay = min(3600.0, 2.0 ** min(attempts, 11))
                connection.execute(
                    """
                    UPDATE callback_outbox SET
                        status='failed', attempts=?, next_attempt_at=?, last_error=?
                    WHERE event_id=?
                    """,
                    (attempts, now + delay, (error or "callback failed")[:500], event_id),
                )

    def cleanup(self, nonce_retention: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock, self._transaction() as connection:
            connection.execute("DELETE FROM p0_cache WHERE expires_at<=?", (now,))
            connection.execute(
                "DELETE FROM request_nonces WHERE seen_at<?", (now - nonce_retention,)
            )
