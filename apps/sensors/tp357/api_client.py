"""
api_client.py — Async client for the Consumo REST API with offline buffering.

If a write fails (NAS/InfluxDB unreachable), the reading is queued locally
in SQLite instead of being dropped. A background task periodically retries
queued readings once the API is reachable again.
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from offline_queue import ReadingQueue

logger = logging.getLogger(__name__)


class ConsumoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        queue_db_path: str = "/data/queue.db",
    ):
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        self._timeout = timeout
        self.queue = ReadingQueue(db_path=queue_db_path)

    async def _post(self, sensor_id: str, payload: dict) -> bool:
        url = f"{self._base}/api/v1/sensors/{sensor_id}/readings"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers)
                resp.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            # 4xx = bad data, retrying won't help — log and drop
            if 400 <= e.response.status_code < 500:
                logger.error(f"Rejected by API for {sensor_id} ({e.response.status_code}): "
                            f"{e.response.text} — dropping, not queuing")
                return True  # treat as "handled" so caller doesn't queue a bad payload
            logger.warning(f"Server error for {sensor_id}: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.warning(f"Network error writing {sensor_id}: {e}")
        return False

    async def write_sensor_reading(
        self,
        sensor_id: str,
        values: dict[str, float],
        timestamp: datetime | None = None,
        note: str | None = None,
        buffer_on_failure: bool = True,
    ) -> bool:
        """
        POST /api/v1/sensors/{sensor_id}/readings.

        On failure (network/server error), the reading is queued locally
        unless buffer_on_failure=False (used by the flush task itself,
        to avoid re-queuing what it's already retrying).
        """
        ts = timestamp or datetime.now(timezone.utc)
        payload: dict = {"values": values, "timestamp": ts.isoformat()}
        if note:
            payload["note"] = note

        ok = await self._post(sensor_id, payload)

        if not ok and buffer_on_failure:
            self.queue.enqueue(sensor_id, values, ts, note)

        return ok

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base}/api/v1/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def flush_queue_loop(self, interval: float = 30.0):
        """
        Background task: periodically retry queued readings.
        Run this with asyncio.create_task() alongside the scanner.
        """
        logger.info(f"Queue flush task started (interval={interval}s)")
        while True:
            await asyncio.sleep(interval)
            pending = self.queue.count()
            if pending == 0:
                continue

            if not await self.health():
                logger.debug(f"API still unreachable — {pending} reading(s) remain queued")
                continue

            logger.info(f"API reachable — flushing {pending} queued reading(s)")
            items = self.queue.pending(limit=100)
            flushed = 0
            for item in items:
                payload = {"values": item.values, "timestamp": item.timestamp}
                if item.note:
                    payload["note"] = item.note

                ok = await self._post(item.sensor_id, payload)
                if ok:
                    self.queue.remove(item.id)
                    flushed += 1
                else:
                    # Stop on first failure — likely API dropped again, retry next cycle
                    break

            if flushed:
                logger.info(f"Flushed {flushed} queued reading(s), "
                            f"{self.queue.count()} remaining")
