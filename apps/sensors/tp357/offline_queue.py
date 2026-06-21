"""
queue.py - Local SQLite buffer for sensor readings.

If the Consumo API (or the NAS InfluxDB behind it) is unreachable, readings
are queued here instead of being lost. A background task periodically
attempts to flush the queue once connectivity returns.

Design goals:
  - Zero external dependencies (sqlite3 is stdlib)
  - Survives container restarts (queue.db on a mounted volume)
  - Simple FIFO per sensor - order doesn't matter much for sensor data,
    but we preserve it anyway for cleaner history.
"""

from __future__ import annotations
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "/data/queue.db"


@dataclass
class QueuedReading:
    id:         int
    sensor_id:  str
    values:     dict[str, float]
    timestamp:  str   # ISO 8601
    note:       str | None
    enqueued_at: float


class ReadingQueue:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_readings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_id   TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    note        TEXT,
                    enqueued_at REAL NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_enqueued_at ON pending_readings(enqueued_at)"
            )

    def enqueue(
        self,
        sensor_id: str,
        values: dict[str, float],
        timestamp: datetime,
        note: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO pending_readings (sensor_id, values_json, timestamp, note, enqueued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sensor_id, json.dumps(values), timestamp.isoformat(), note, time.time()),
            )
        logger.info(f"Queued reading for {sensor_id} (offline buffer)")

    def pending(self, limit: int = 100) -> list[QueuedReading]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pending_readings ORDER BY enqueued_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                QueuedReading(
                    id=row["id"],
                    sensor_id=row["sensor_id"],
                    values=json.loads(row["values_json"]),
                    timestamp=row["timestamp"],
                    note=row["note"],
                    enqueued_at=row["enqueued_at"],
                )
                for row in rows
            ]

    def remove(self, reading_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM pending_readings WHERE id = ?", (reading_id,))

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM pending_readings").fetchone()
            return row[0]
