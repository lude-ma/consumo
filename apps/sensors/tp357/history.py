"""
history.py — Active GATT connection to fetch stored history from TP357 sensors.

The TP357 stores up to 1 year of data accessible via three GATT characteristics:
  - "day"  : minute-by-minute, last 24 hours
  - "week" : hour-by-hour,     last 7 days
  - "year" : hour-by-hour,     last 365 days

Based on reverse-engineering documented at https://github.com/pasky/tp357
"""

from __future__ import annotations
import asyncio
import logging
import struct
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from bleak import BleakClient, BleakError
from tp357_parser import TP357Reading

logger = logging.getLogger(__name__)

# GATT UUIDs for TP357 history (from pasky/tp357 reverse engineering)
HISTORY_SERVICE_UUID    = "0000aa20-0000-1000-8000-00805f9b34fb"
HISTORY_CHAR_UUID       = "0000aa21-0000-1000-8000-00805f9b34fb"
HISTORY_NOTIFY_UUID     = "0000aa22-0000-1000-8000-00805f9b34fb"

# Commands to request different history ranges
HISTORY_COMMANDS = {
    "day":  bytes([0x01]),   # minute-by-minute, last 24h
    "week": bytes([0x02]),   # hour-by-hour,     last 7 days
    "year": bytes([0x03]),   # hour-by-hour,     last 365 days
}


@dataclass
class HistoryPoint:
    timestamp:   datetime
    temperature: float
    humidity:    int


async def fetch_history(
    mac: str,
    mode: str = "year",
    timeout: float = 60.0,
) -> list[HistoryPoint]:
    """
    Connect to a TP357 sensor and download its stored history.

    Args:
        mac:     Bluetooth MAC address
        mode:    "day" | "week" | "year"
        timeout: Connection + download timeout in seconds

    Returns:
        List of HistoryPoint, oldest first. Empty list on failure.
    """
    if mode not in HISTORY_COMMANDS:
        raise ValueError(f"mode must be one of {list(HISTORY_COMMANDS)}")

    points: list[HistoryPoint] = []
    received_packets: list[bytes] = []
    done = asyncio.Event()

    def notification_handler(sender, data: bytes):
        # Last packet is a single 0x00 byte (end-of-transmission marker)
        if data == bytes([0x00]) or len(data) == 0:
            done.set()
            return
        received_packets.append(data)

    logger.info(f"Connecting to {mac} for history ({mode})...")
    try:
        async with BleakClient(mac, timeout=timeout) as client:
            logger.info(f"Connected to {mac}")

            # Enable notifications
            await client.start_notify(HISTORY_NOTIFY_UUID, notification_handler)

            # Request history
            await client.write_gatt_char(
                HISTORY_CHAR_UUID,
                HISTORY_COMMANDS[mode],
                response=True,
            )

            # Wait for all packets
            try:
                await asyncio.wait_for(done.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"{mac}: history download timed out, parsing what we have")

            await client.stop_notify(HISTORY_NOTIFY_UUID)

    except BleakError as e:
        logger.error(f"BLE error connecting to {mac}: {e}")
        return []
    except asyncio.TimeoutError:
        logger.error(f"Connection timeout for {mac}")
        return []

    # Parse packets
    now = datetime.now(timezone.utc)
    interval = timedelta(minutes=1) if mode == "day" else timedelta(hours=1)

    # Each packet contains multiple 3-byte records: temp(int16) + humidity(uint8)
    raw_records: list[tuple[float, int]] = []
    for packet in received_packets:
        i = 0
        while i + 2 < len(packet):
            raw_temp = struct.unpack_from("<h", packet, i)[0]
            humidity  = packet[i + 2]
            temp = round(raw_temp / 10.0, 1)
            if -40 <= temp <= 85 and 0 <= humidity <= 100:
                raw_records.append((temp, humidity))
            i += 3

    # Reconstruct timestamps — records are newest first, step back by interval
    for idx, (temp, humidity) in enumerate(raw_records):
        ts = now - interval * idx
        points.append(HistoryPoint(timestamp=ts, temperature=temp, humidity=humidity))

    # Return oldest first
    points.reverse()
    logger.info(f"{mac}: fetched {len(points)} history points ({mode})")
    return points


async def fetch_all_history(
    sensors: list[dict],
    mode: str = "year",
    concurrency: int = 3,
) -> dict[str, list[HistoryPoint]]:
    """
    Fetch history from multiple sensors with limited concurrency.
    BLE doesn't support many parallel connections well.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, list[HistoryPoint]] = {}

    async def fetch_one(sensor: dict):
        mac       = sensor["mac"]
        sensor_id = sensor["sensor_id"]
        async with semaphore:
            points = await fetch_history(mac, mode=mode)
            results[sensor_id] = points

    await asyncio.gather(*[fetch_one(s) for s in sensors if s.get("enabled", True)])
    return results
