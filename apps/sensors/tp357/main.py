"""
main.py — TP357 BLE Scanner for Consumo

Modes:
  scan     (default) Passive advertisement scanning, writes to API every N seconds
  history  Active GATT connect to all sensors, imports stored history (up to 1 year)
  discover Scan for any TP357 devices nearby and print their MAC addresses
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from tp357_parser import parse_advertisement, TP357Reading
from api_client import ConsumoClient
from history import fetch_all_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tp357")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    path = Path(os.environ.get("CONSUMO_SENSORS_PATH", "/config/sensors.yml"))
    if not path.exists():
        # Dev fallback
        path = Path(__file__).parent.parent.parent.parent / "config" / "sensors.yml"
    if not path.exists():
        logger.error(f"sensors.yml not found at {path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def build_mac_map(sensors: list[dict]) -> dict[str, str]:
    """MAC (uppercase) → sensor_id"""
    return {
        s["mac"].upper(): s["sensor_id"]
        for s in sensors
        if s.get("enabled", True)
    }


# ---------------------------------------------------------------------------
# Mode: discover
# ---------------------------------------------------------------------------

async def discover(scan_seconds: int = 15):
    """Scan for TP357 devices and print their MAC addresses."""
    logger.info(f"Scanning for TP357 devices for {scan_seconds} seconds...")
    found: dict[str, str] = {}  # mac → name

    def callback(device: BLEDevice, adv: AdvertisementData):
        reading = parse_advertisement(adv.manufacturer_data)
        if reading and device.address not in found:
            found[device.address] = device.name or "TP357"
            print(f"  Found: {device.address}  name={device.name}  "
                  f"temp={reading.temperature}°C  hum={reading.humidity}%  "
                  f"bat={reading.battery}%")

    async with BleakScanner(callback):
        await asyncio.sleep(scan_seconds)

    print(f"\nFound {len(found)} TP357 sensor(s).")
    if found:
        print("\nAdd to config/sensors.yml:")
        for mac, name in found.items():
            print(f"  - mac: \"{mac}\"")
            print(f"    sensor_id: <choose_a_name>")
            print(f"    enabled: true")


# ---------------------------------------------------------------------------
# Mode: scan (passive, continuous)
# ---------------------------------------------------------------------------

async def scan(cfg: dict, client: ConsumoClient):
    """
    Passively listen to BLE advertisements.
    Deduplicate: write at most once per sensor per write_interval seconds.
    """
    sensors    = cfg["sensors"]
    settings   = cfg.get("settings", {})
    interval   = settings.get("write_interval", 60)
    mac_map    = build_mac_map(sensors)
    last_write: dict[str, float] = {}

    logger.info(f"Starting passive scan — {len(mac_map)} sensors registered, "
                f"write interval={interval}s")

    # Wait for API to be ready
    for attempt in range(10):
        if await client.health():
            logger.info("Consumo API is reachable")
            break
        logger.warning(f"API not reachable (attempt {attempt+1}/10), retrying in 5s...")
        await asyncio.sleep(5)

    def callback(device: BLEDevice, adv: AdvertisementData):
        mac = device.address.upper()
        sensor_id = mac_map.get(mac)
        if not sensor_id:
            return

        reading: TP357Reading | None = parse_advertisement(adv.manufacturer_data)
        if not reading:
            return

        now = asyncio.get_event_loop().time()
        if now - last_write.get(sensor_id, 0) < interval:
            return
        last_write[sensor_id] = now

        # Schedule write without blocking the BLE callback
        asyncio.ensure_future(_write(client, sensor_id, reading))

    async with BleakScanner(callback):
        logger.info("Scanning... (press Ctrl+C to stop)")
        while True:
            await asyncio.sleep(60)


async def _write(client: ConsumoClient, sensor_id: str, reading: TP357Reading):
    values = {
        "temperature": reading.temperature,
        "humidity":    float(reading.humidity),
        "battery":     float(reading.battery),
    }
    ok = await client.write_sensor_reading(
        sensor_id=sensor_id,
        values=values,
        timestamp=datetime.now(timezone.utc),
    )
    if ok:
        logger.info(f"{sensor_id}: {reading.temperature}°C  {reading.humidity}%RH  "
                    f"bat={reading.battery}%")
    else:
        logger.warning(f"{sensor_id}: failed to write reading — will retry next interval")


# ---------------------------------------------------------------------------
# Mode: history
# ---------------------------------------------------------------------------

async def history(cfg: dict, client: ConsumoClient, mode: str = "year"):
    """Connect to each sensor and import stored history."""
    sensors = [s for s in cfg["sensors"] if s.get("enabled", True)]
    logger.info(f"Fetching {mode} history from {len(sensors)} sensor(s)...")

    results = await fetch_all_history(sensors, mode=mode)

    total = 0
    for sensor_id, points in results.items():
        logger.info(f"{sensor_id}: writing {len(points)} historical points...")
        written = 0
        for point in points:
            ok = await client.write_sensor_reading(
                sensor_id=sensor_id,
                values={
                    "temperature": point.temperature,
                    "humidity":    float(point.humidity),
                },
                timestamp=point.timestamp,
            )
            if ok:
                written += 1
            else:
                # Brief back-off on API errors
                await asyncio.sleep(0.5)
        logger.info(f"{sensor_id}: {written}/{len(points)} points written")
        total += written

    logger.info(f"History import complete — {total} total points written")


async def _run_scan_with_flush(cfg: dict, client: ConsumoClient):
    """Run the passive scanner and the offline-queue flush task side by side."""
    settings = cfg.get("settings", {})
    flush_interval = settings.get("retry_interval", 30)

    await asyncio.gather(
        scan(cfg, client),
        client.flush_queue_loop(interval=flush_interval),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TP357 BLE Scanner for Consumo")
    parser.add_argument(
        "--mode",
        choices=["scan", "history", "discover"],
        default="scan",
        help="scan: passive continuous scan (default) | "
             "history: import stored sensor data | "
             "discover: find TP357 devices nearby",
    )
    parser.add_argument(
        "--history-mode",
        choices=["day", "week", "year"],
        default="year",
        help="History range to fetch (only with --mode history)",
    )
    args = parser.parse_args()

    if args.mode == "discover":
        asyncio.run(discover())
        return

    cfg = load_config()
    api_url = os.environ.get("CONSUMO_API_URL", "http://consumo-api:8200")
    api_key = os.environ.get("CONSUMO_API_KEY", "")
    queue_db_path = os.environ.get("CONSUMO_QUEUE_DB", "/data/queue.db")
    api_client = ConsumoClient(base_url=api_url, api_key=api_key, queue_db_path=queue_db_path)

    if args.mode == "scan":
        try:
            asyncio.run(_run_scan_with_flush(cfg, api_client))
        except KeyboardInterrupt:
            logger.info("Stopped.")

    elif args.mode == "history":
        asyncio.run(history(cfg, api_client, mode=args.history_mode))


if __name__ == "__main__":
    main()
