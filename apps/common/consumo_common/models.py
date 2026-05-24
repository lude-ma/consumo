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
    label:       str
    unit:        str
    icon:        str
    color:       str
    meter_type:  MeterType
    placeholder: str
    hint:        str


# ---------------------------------------------------------------------------
# Central meter registry — the single source of truth for the whole project.
# Add new meters here; API and Web UI pick them up automatically.
# ---------------------------------------------------------------------------
METERS: dict[str, MeterMeta] = {
    "strom": MeterMeta(
        label="Strom",
        unit="kWh",
        icon="⚡",
        color="#f59e0b",
        meter_type=MeterType.COUNTER,
        placeholder="z.B. 12345.6",
        hint="Aktueller Zählerstand (steigt monoton)",
    ),
    "wasser": MeterMeta(
        label="Wasser",
        unit="m³",
        icon="💧",
        color="#3b82f6",
        meter_type=MeterType.COUNTER,
        placeholder="z.B. 987.3",
        hint="Aktueller Zählerstand (steigt monoton)",
    ),
    "pellets": MeterMeta(
        label="Pellets",
        unit="kg",
        icon="🪵",
        color="#a16207",
        meter_type=MeterType.STORAGE,
        placeholder="z.B. 2500",
        hint="Aktueller Füllstand im Tank",
    ),
}

# Human-readable labels for meter types
METER_TYPE_LABELS: dict[MeterType, tuple[str, str]] = {
    MeterType.COUNTER: ("Zählerstand", "📟"),
    MeterType.STORAGE: ("Lagerbestand", "🗄️"),
    MeterType.SENSOR:  ("Messwert",     "🌡️"),
}
