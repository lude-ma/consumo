"""
tp357_parser.py — Parse TP357 BLE advertisement manufacturer data.

Advertisement format (Manufacturer Data, company ID 0x0001):
  Bytes  0-1:  Company ID (little-endian, usually 0x0001)
  Bytes  2-11: Device name as ASCII ("TP357 (XXXX)")
  Byte   12:   ??? (flags/version)
  Bytes 13-14: Temperature × 10 as int16, little-endian  (e.g. 0x00D4 = 212 → 21.2°C)
  Byte   15:   Humidity as uint8  (e.g. 0x3A = 58 → 58%)
  Byte   16:   Battery  as uint8  (e.g. 0x64 = 100 → 100%)

References:
  https://github.com/custom-components/ble_monitor/issues/961
  https://github.com/pasky/tp357
"""

from __future__ import annotations
import struct
from dataclasses import dataclass


@dataclass
class TP357Reading:
    temperature: float   # °C
    humidity:    int     # %RH
    battery:     int     # %


def parse_advertisement(manufacturer_data: dict[int, bytes]) -> TP357Reading | None:
    """
    Extract temperature, humidity and battery from raw BLE manufacturer data.
    Returns None if the data doesn't match the expected TP357 format.
    """
    for _company_id, data in manufacturer_data.items():
        reading = _try_parse(data)
        if reading is not None:
            return reading
    return None


def _try_parse(data: bytes) -> TP357Reading | None:
    # Minimum length check
    if len(data) < 17:
        return None

    # Sanity-check: bytes 2-6 should be "TP357" ASCII
    try:
        name_prefix = data[2:7].decode("ascii", errors="replace")
    except Exception:
        return None

    if name_prefix != "TP357":
        return None

    try:
        # Temperature: int16 little-endian at offset 13, divide by 10
        raw_temp = struct.unpack_from("<h", data, 13)[0]
        temperature = round(raw_temp / 10.0, 1)

        humidity = data[15]
        battery  = data[16]

        # Basic range validation
        if not (-40 <= temperature <= 85):
            return None
        if not (0 <= humidity <= 100):
            return None
        if not (0 <= battery <= 100):
            return None

        return TP357Reading(temperature=temperature, humidity=humidity, battery=battery)

    except (struct.error, IndexError):
        return None
