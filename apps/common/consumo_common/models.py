from dataclasses import dataclass
from enum import Enum


class MeterType(str, Enum):
    """
    counter  – monotonically increasing absolute reading (e.g. electricity, water meter)
               Consumption = difference between successive readings.
               Negative deltas are ignored (meter replacement).

    storage  – level that rises on refill and falls on consumption (e.g. pellet tank)
               Refills   = positive deltas
               Consumed  = negative deltas (sign-flipped for display)

    sensor   – arbitrary measurement, no consumption semantics (e.g. temperature, pressure)
               Values are plotted directly.
    """
    COUNTER = "counter"
    STORAGE = "storage"
    SENSOR  = "sensor"


@dataclass(frozen=True)
class MeterMeta:
    unit:        str
    icon:        str
    color:       str
    meter_type:  MeterType


# ---------------------------------------------------------------------------
# Central meter registry — the single source of truth for the whole project.
# Labels, hints and placeholders live in apps/web/i18n/{lang}.json under the
# keys  meter_{id}_label | meter_{id}_hint | meter_{id}_placeholder
# Add new meters here; API and Web UI pick them up automatically.
# ---------------------------------------------------------------------------
METERS: dict[str, MeterMeta] = {
    "strom": MeterMeta(
        unit="kWh",
        icon="⚡",
        color="#f59e0b",
        meter_type=MeterType.COUNTER,
    ),
    "wasser": MeterMeta(
        unit="m³",
        icon="💧",
        color="#3b82f6",
        meter_type=MeterType.COUNTER,
    ),
    "pellets": MeterMeta(
        unit="kg",
        icon="🪵",
        color="#a16207",
        meter_type=MeterType.STORAGE,
    ),
}

# Icons for meter types — language-neutral, used by templates
METER_TYPE_ICONS: dict[MeterType, str] = {
    MeterType.COUNTER: "📟",
    MeterType.STORAGE: "🗄️",
    MeterType.SENSOR:  "🌡️",
}
