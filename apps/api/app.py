import os
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, HTTPException, Security, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from consumo_common.models import METERS, MeterType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INFLUXDB_URL    = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN  = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG    = os.environ.get("INFLUXDB_ORG", "home")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "energy")

# Comma-separated list of valid API keys, e.g. "key1,key2"
_RAW_KEYS = os.environ.get("API_KEYS", "")
API_KEYS: set[str] = {k.strip() for k in _RAW_KEYS.split(",") if k.strip()}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Consumo API",
    description="REST API for tracking meter readings, storage levels and sensor values.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: Annotated[str | None, Security(api_key_header)] = None) -> str:
    if not API_KEYS:
        raise HTTPException(status_code=500, detail="No API keys configured on server")
    if not key or key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")
    return key


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MeterOut(BaseModel):
    id:         str
    unit:       str
    icon:       str
    color:      str
    meter_type: str


class ReadingIn(BaseModel):
    value:     float
    timestamp: datetime | None = None
    note:      str | None = None

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, v):
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("value must be a finite number")
        return v


class ReadingOut(BaseModel):
    timestamp: str
    value:     float
    unit:      str
    note:      str | None


class ReadingCreated(BaseModel):
    meter:     str
    value:     float
    unit:      str
    timestamp: str
    note:      str | None


class MetaEnvelope(BaseModel):
    meter:      str | None = None
    meter_type: str | None = None
    unit:       str | None = None
    count:      int | None = None


class Response[T](BaseModel):
    data: T
    meta: MetaEnvelope | None = None


# ---------------------------------------------------------------------------
# InfluxDB helpers
# ---------------------------------------------------------------------------

def get_client() -> InfluxDBClient:
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


def _meter_out(key: str) -> MeterOut:
    m = METERS[key]
    return MeterOut(id=key, unit=m.unit, icon=m.icon,
                    color=m.color, meter_type=m.meter_type.value)


def _require_meter(meter: str):
    if meter not in METERS:
        raise HTTPException(status_code=404, detail=f"Unknown meter '{meter}'")
    return METERS[meter]


def _scalar(qapi, query: str) -> float | None:
    for table in qapi.query(query, org=INFLUXDB_ORG):
        for record in table.records:
            v = record.get_value()
            return float(v) if v is not None else None
    return None


def _to_flux_time(t: str) -> str:
    if t.startswith("-") or t == "now()":
        return t
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return t


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["system"])
def health():
    try:
        with get_client() as client:
            client.ping()
        return {"data": {"status": "ok", "influxdb": "connected"}}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/v1/meters", tags=["meters"],
         dependencies=[Security(require_api_key)])
def list_meters() -> Response[list[MeterOut]]:
    meters = [_meter_out(k) for k in METERS]
    return Response(data=meters, meta=MetaEnvelope(count=len(meters)))


@app.get("/api/v1/meters/{meter}", tags=["meters"],
         dependencies=[Security(require_api_key)])
def get_meter(meter: str) -> Response[MeterOut]:
    _require_meter(meter)
    return Response(data=_meter_out(meter))


@app.post("/api/v1/meters/{meter}/readings", status_code=201, tags=["readings"],
          dependencies=[Security(require_api_key)])
def create_reading(meter: str, body: ReadingIn) -> Response[ReadingCreated]:
    meta = _require_meter(meter)

    # Business-rule validation
    if meta.meter_type in (MeterType.COUNTER, MeterType.STORAGE) and body.value < 0:
        raise HTTPException(status_code=422,
                            detail=f"{meta.meter_type.value.capitalize()} value must be >= 0")

    ts = body.timestamp or datetime.now(timezone.utc)

    try:
        with get_client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            point = (
                Point(meter)
                .tag("unit", meta.unit)
                .tag("meter_type", meta.meter_type.value)
                .field("value", body.value)
                .time(ts, WritePrecision.S)
            )
            if body.note:
                point = point.field("note", body.note.strip())
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as e:
        logger.error(f"Write error for {meter}: {e}")
        raise HTTPException(status_code=502, detail="Failed to write to database")

    return Response(data=ReadingCreated(
        meter=meter, value=body.value, unit=meta.unit,
        timestamp=ts.isoformat(), note=body.note,
    ))


@app.get("/api/v1/meters/{meter}/readings", tags=["readings"],
         dependencies=[Security(require_api_key)])
def get_readings(
    meter: str,
    start: Annotated[str, Query(description="Flux duration or ISO 8601, e.g. -30d or 2024-01-01")] = "-30d",
    end:   Annotated[str, Query(description="Flux duration or ISO 8601, e.g. now() or 2024-12-31")] = "now()",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Response[list[ReadingOut]]:
    _require_meter(meter)

    desc = "true" if order == "desc" else "false"
    # pivot to get both value and note fields per timestamp
    query = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: {_to_flux_time(start)}, stop: {_to_flux_time(end)})
  |> filter(fn: (r) => r._measurement == "{meter}")
  |> filter(fn: (r) => r._field == "value" or r._field == "note")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: {desc})
  |> limit(n: {limit})
'''
    try:
        with get_client() as client:
            tables = client.query_api().query(query, org=INFLUXDB_ORG)
    except Exception as e:
        logger.error(f"Query error for {meter}: {e}")
        raise HTTPException(status_code=502, detail="Failed to query database")

    rows = [
        ReadingOut(
            timestamp=record.get_time().isoformat(),
            value=record.values.get("value", 0.0),
            unit=record.values.get("unit", ""),
            note=record.values.get("note") or None,
        )
        for table in tables
        for record in table.records
    ]

    return Response(data=rows, meta=MetaEnvelope(meter=meter, count=len(rows)))


@app.get("/api/v1/meters/{meter}/stats", tags=["stats"],
         dependencies=[Security(require_api_key)])
def get_stats(meter: str) -> Response[dict]:
    meta = _require_meter(meter)
    base = (
        f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -10y)'
        f' |> filter(fn: (r) => r._measurement == "{meter}" and r._field == "value")'
    )

    try:
        with get_client() as client:
            qapi = client.query_api()
            s = lambda q: _scalar(qapi, q)  # noqa: E731

            if meta.meter_type == MeterType.COUNTER:
                stats = {
                    "last_30d":      s(f'{base} |> range(start: -31d)  |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> sum()'),
                    "last_365d":     s(f'{base} |> range(start: -366d) |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> sum()'),
                    "avg_per_month": s(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> aggregateWindow(every: 1mo, fn: sum, createEmpty: false) |> mean()'),
                    "avg_per_year":  s(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> aggregateWindow(every: 1y,  fn: sum, createEmpty: false) |> mean()'),
                }
            elif meta.meter_type == MeterType.STORAGE:
                stats = {
                    "current_level":         s(f'{base} |> last()'),
                    "total_refilled":        s(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value > 0) |> sum()'),
                    "total_consumed":        s(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value < 0) |> map(fn: (r) => ({{ r with _value: r._value * -1.0 }})) |> sum()'),
                    "avg_consumed_per_month": s(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value < 0) |> map(fn: (r) => ({{ r with _value: r._value * -1.0 }})) |> aggregateWindow(every: 1mo, fn: sum, createEmpty: false) |> mean()'),
                }
            else:  # sensor
                stats = {
                    "last": s(f'{base} |> last()'),
                    "min":  s(f'{base} |> min()'),
                    "max":  s(f'{base} |> max()'),
                    "mean": s(f'{base} |> mean()'),
                }

    except Exception as e:
        logger.error(f"Stats error for {meter}: {e}")
        raise HTTPException(status_code=502, detail="Failed to compute stats")

    return Response(
        data=stats,
        meta=MetaEnvelope(meter=meter, meter_type=meta.meter_type.value, unit=meta.unit),
    )


# ---------------------------------------------------------------------------
# Multi-value readings (for sensors with multiple fields e.g. TP357)
# POST /api/v1/sensors/{sensor_id}/readings
# Body: { "values": {"temperature": 21.5, "humidity": 58, "battery": 95}, "timestamp": "..." }
# ---------------------------------------------------------------------------

class MultiReadingIn(BaseModel):
    values:    dict[str, float]
    timestamp: datetime | None = None
    note:      str | None = None

    @field_validator("values")
    @classmethod
    def values_must_be_finite(cls, v):
        import math
        for key, val in v.items():
            if math.isnan(val) or math.isinf(val):
                raise ValueError(f"value for '{key}' must be a finite number")
        return v


class MultiReadingCreated(BaseModel):
    sensor:    str
    values:    dict[str, float]
    timestamp: str
    note:      str | None


class SensorOut(BaseModel):
    id:          str
    description: str
    fields:      list[str]


@app.get("/api/v1/sensors", tags=["sensors"],
         dependencies=[Security(require_api_key)])
def list_sensors() -> Response[list[SensorOut]]:
    """List all registered multi-field sensors (e.g. TP357 with temp+humidity)."""
    from consumo_common.models import SENSORS
    sensors = [
        SensorOut(id=k, description=v.description, fields=v.fields)
        for k, v in SENSORS.items()
    ]
    return Response(data=sensors, meta=MetaEnvelope(count=len(sensors)))


@app.post("/api/v1/sensors/{sensor_id}/readings", status_code=201, tags=["sensors"],
          dependencies=[Security(require_api_key)])
def create_sensor_reading(sensor_id: str, body: MultiReadingIn) -> Response[MultiReadingCreated]:
    """
    Write a multi-field reading for a sensor.
    All fields are stored as separate InfluxDB fields on the same measurement+timestamp.
    """
    from consumo_common.models import SENSORS
    if sensor_id not in SENSORS:
        raise HTTPException(status_code=404, detail=f"Unknown sensor '{sensor_id}'")

    sensor = SENSORS[sensor_id]

    # Warn about unknown fields but don't reject - allows forward-compat
    unknown = set(body.values) - set(sensor.fields)
    if unknown:
        logger.warning(f"Sensor '{sensor_id}' received unknown fields: {unknown}")

    ts = body.timestamp or datetime.now(timezone.utc)

    try:
        with get_client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            point = Point(sensor_id).tag("sensor_type", sensor.sensor_type).time(ts, WritePrecision.S)
            for field, val in body.values.items():
                point = point.field(field, float(val))
            if body.note:
                point = point.field("note", body.note.strip())
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as e:
        logger.error(f"Write error for sensor {sensor_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to write to database")

    return Response(data=MultiReadingCreated(
        sensor=sensor_id, values=body.values,
        timestamp=ts.isoformat(), note=body.note,
    ))


@app.get("/api/v1/sensors/{sensor_id}/readings", tags=["sensors"],
         dependencies=[Security(require_api_key)])
def get_sensor_readings(
    sensor_id: str,
    start: Annotated[str, Query(description="Flux duration or ISO 8601")] = "-30d",
    end:   Annotated[str, Query(description="Flux duration or ISO 8601")] = "now()",
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Response[list[dict]]:
    from consumo_common.models import SENSORS
    if sensor_id not in SENSORS:
        raise HTTPException(status_code=404, detail=f"Unknown sensor '{sensor_id}'")

    desc = "true" if order == "desc" else "false"
    query = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: {_to_flux_time(start)}, stop: {_to_flux_time(end)})
  |> filter(fn: (r) => r._measurement == "{sensor_id}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: {desc})
  |> limit(n: {limit})
'''
    try:
        with get_client() as client:
            tables = client.query_api().query(query, org=INFLUXDB_ORG)
    except Exception as e:
        logger.error(f"Query error for sensor {sensor_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to query database")

    rows = []
    for table in tables:
        for record in table.records:
            row = {"timestamp": record.get_time().isoformat()}
            for field in SENSORS[sensor_id].fields:
                if field in record.values:
                    row[field] = record.values[field]
            rows.append(row)

    return Response(data=rows, meta=MetaEnvelope(meter=sensor_id, count=len(rows)))
