"""
Consumo — shared meter/sensor registry.

The source of truth is config/meters.yml at the repo root.
This module loads and validates it, exposing METERS and SENSORS dicts
that the API and Web UI consume — identical interface to the old hardcoded version.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class MeterType(str, Enum):
    """
    counter     – monotonically increasing absolute reading (e.g. electricity, water meter)
                  Consumption = difference between successive readings.
                  Negative deltas are ignored (meter replacement).

    storage     – level that rises on refill and falls on consumption (e.g. pellet tank)
                  Refills   = positive deltas
                  Consumed  = negative deltas (sign-flipped for display)

    sensor      – arbitrary measurement, no consumption semantics (e.g. temperature, pressure)
                  Values are plotted directly.

    multisensor – multiple fields per reading (TP357: temp + humidity + battery)
    """
    COUNTER     = "counter"
    STORAGE     = "storage"
    SENSOR      = "sensor"
    MULTISENSOR = "multisensor"


@dataclass(frozen=True)
class MeterMeta:
    unit:       str
    icon:       str
    color:      str
    meter_type: MeterType


@dataclass(frozen=True)
class SensorMeta:
    icon:        str
    color:       str
    meter_type:  MeterType          # always MULTISENSOR
    sensor_type: str                # e.g. "tp357"
    fields:      dict[str, str]     # field_name → unit


# Icons for meter types — language-neutral, used by templates
METER_TYPE_ICONS: dict[MeterType, str] = {
    MeterType.COUNTER:     "📟",
    MeterType.STORAGE:     "🗄️",
    MeterType.SENSOR:      "🌡️",
    MeterType.MULTISENSOR: "🌡️",
}


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _find_config() -> Path:
    """
    Search for meters.yml in likely locations:
      1. CONSUMO_CONFIG_PATH env var (explicit override)
      2. /config/meters.yml           (Docker volume mount)
      3. repo_root/config/meters.yml  (local dev)
    """
    explicit = os.environ.get("CONSUMO_CONFIG_PATH")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        raise FileNotFoundError(f"CONSUMO_CONFIG_PATH set but not found: {p}")

    # Walk up from this file to find repo root (has a config/ dir)
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "config" / "meters.yml"
        if candidate.exists():
            return candidate

    # Docker default
    docker_path = Path("/config/meters.yml")
    if docker_path.exists():
        return docker_path

    raise FileNotFoundError(
        "meters.yml not found. Set CONSUMO_CONFIG_PATH or mount config/ volume."
    )


def _load(path: Path) -> tuple[dict[str, MeterMeta], dict[str, SensorMeta]]:
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    meters: dict[str, MeterMeta] = {}
    sensors: dict[str, SensorMeta] = {}

    for key, cfg in (raw.get("meters") or {}).items():
        mt = MeterType(cfg["meter_type"])
        meters[key] = MeterMeta(
            unit=cfg.get("unit", ""),
            icon=cfg.get("icon", ""),
            color=cfg.get("color", "#888888"),
            meter_type=mt,
        )

    for key, cfg in (raw.get("sensors") or {}).items():
        sensors[key] = SensorMeta(
            icon=cfg.get("icon", "🌡️"),
            color=cfg.get("color", "#888888"),
            meter_type=MeterType.MULTISENSOR,
            sensor_type=cfg.get("sensor_type", "unknown"),
            fields=cfg.get("fields", {}),
        )

    return meters, sensors


# ---------------------------------------------------------------------------
# Module-level exports — loaded once at import time
# ---------------------------------------------------------------------------

_config_path = _find_config()
METERS, SENSORS = _load(_config_path)

# Combined view — useful for iteration in templates
ALL_METERS: dict[str, MeterMeta | SensorMeta] = {**METERS, **SENSORS}


def reload() -> None:
    """Reload config from disk — useful in tests or after hot-edits."""
    global METERS, SENSORS, ALL_METERS
    METERS, SENSORS = _load(_config_path)
    ALL_METERS = {**METERS, **SENSORS}
