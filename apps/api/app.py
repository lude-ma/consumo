import os
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from consumo_common.models import METERS, MeterType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

INFLUXDB_URL    = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN  = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG    = os.environ.get("INFLUXDB_ORG", "home")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "energy")

# Comma-separated list of valid API keys, e.g. "key1,key2"
_RAW_KEYS = os.environ.get("API_KEYS", "")
API_KEYS: set[str] = {k.strip() for k in _RAW_KEYS.split(",") if k.strip()}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEYS:
            return error("api_not_configured", "No API keys configured on server", 500)
        key = request.headers.get("X-API-Key", "")
        if key not in API_KEYS:
            return error("unauthorized", "Invalid or missing X-API-Key header", 401)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(data, meta: dict = None, status: int = 200):
    body = {"data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def error(code: str, message: str, status: int):
    return jsonify({"error": code, "message": message, "status": status}), status


def get_client():
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


def _meter_dict(key: str) -> dict:
    m = METERS[key]
    return {
        "id":         key,
        "label":      m.label,
        "unit":       m.unit,
        "icon":       m.icon,
        "color":      m.color,
        "meter_type": m.meter_type.value,
        "hint":       m.hint,
    }


# ---------------------------------------------------------------------------
# Routes — /api/v1
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health():
    try:
        with get_client() as client:
            client.ping()
        return ok({"status": "ok", "influxdb": "connected"})
    except Exception as e:
        return error("influxdb_unavailable", str(e), 503)


@app.get("/api/v1/meters")
@require_api_key
def list_meters():
    return ok([_meter_dict(k) for k in METERS], meta={"count": len(METERS)})


@app.get("/api/v1/meters/<meter>")
@require_api_key
def get_meter(meter: str):
    if meter not in METERS:
        return error("not_found", f"Unknown meter '{meter}'", 404)
    return ok(_meter_dict(meter))


@app.post("/api/v1/meters/<meter>/readings")
@require_api_key
def create_reading(meter: str):
    if meter not in METERS:
        return error("not_found", f"Unknown meter '{meter}'", 404)

    body = request.get_json(silent=True) or {}

    # --- validate value ---
    raw = body.get("value")
    if raw is None:
        return error("missing_field", "'value' is required", 400)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return error("invalid_value", "'value' must be a number", 400)

    meta = METERS[meter]
    if meta.meter_type == MeterType.COUNTER and value < 0:
        return error("invalid_value", "Counter readings must be >= 0", 400)
    if meta.meter_type == MeterType.STORAGE and value < 0:
        return error("invalid_value", "Storage level must be >= 0", 400)

    # --- timestamp ---
    ts_raw = body.get("timestamp")
    if ts_raw:
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            return error("invalid_timestamp",
                         "Use ISO 8601 format, e.g. 2024-03-15T08:30:00Z", 400)
    else:
        ts = datetime.now(timezone.utc)

    note = str(body.get("note", "")).strip()

    # --- write ---
    try:
        with get_client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            point = (
                Point(meter)
                .tag("unit", meta.unit)
                .tag("meter_type", meta.meter_type.value)
                .field("value", value)
                .time(ts, WritePrecision.SECONDS)
            )
            if note:
                point = point.tag("note", note)
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as e:
        logger.error(f"Write error for {meter}: {e}")
        return error("write_error", "Failed to write to database", 502)

    return ok({
        "meter":     meter,
        "value":     value,
        "unit":      meta.unit,
        "timestamp": ts.isoformat(),
        "note":      note or None,
    }, status=201)


@app.get("/api/v1/meters/<meter>/readings")
@require_api_key
def get_readings(meter: str):
    if meter not in METERS:
        return error("not_found", f"Unknown meter '{meter}'", 404)

    # Query params
    start  = request.args.get("start", "-30d")
    end    = request.args.get("end",   "now()")
    limit  = request.args.get("limit", "100")
    order  = request.args.get("order", "desc")

    try:
        limit = max(1, min(int(limit), 1000))
    except ValueError:
        return error("invalid_param", "'limit' must be an integer (1–1000)", 400)

    # Normalise start/end to Flux-compatible strings
    def to_flux_time(t: str) -> str:
        if t.startswith("-") or t == "now()":
            return t
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return t

    flux_start = to_flux_time(start)
    flux_end   = to_flux_time(end)
    desc       = "true" if order == "desc" else "false"

    query = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: {flux_start}, stop: {flux_end})
  |> filter(fn: (r) => r._measurement == "{meter}")
  |> filter(fn: (r) => r._field == "value")
  |> sort(columns: ["_time"], desc: {desc})
  |> limit(n: {limit})
'''
    try:
        with get_client() as client:
            tables = client.query_api().query(query, org=INFLUXDB_ORG)
    except Exception as e:
        logger.error(f"Query error for {meter}: {e}")
        return error("query_error", "Failed to query database", 502)

    rows = []
    for table in tables:
        for record in table.records:
            rows.append({
                "timestamp": record.get_time().isoformat(),
                "value":     record.get_value(),
                "unit":      record.values.get("unit", ""),
                "note":      record.values.get("note") or None,
            })

    return ok(rows, meta={"meter": meter, "count": len(rows)})


@app.get("/api/v1/meters/<meter>/stats")
@require_api_key
def get_stats(meter: str):
    if meter not in METERS:
        return error("not_found", f"Unknown meter '{meter}'", 404)

    meta = METERS[meter]

    try:
        with get_client() as client:
            qapi = client.query_api()

            def scalar(query: str) -> float | None:
                tables = qapi.query(query, org=INFLUXDB_ORG)
                for t in tables:
                    for r in t.records:
                        v = r.get_value()
                        return float(v) if v is not None else None
                return None

            base = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -10y) |> filter(fn: (r) => r._measurement == "{meter}" and r._field == "value")'

            if meta.meter_type == MeterType.COUNTER:
                stats = {
                    "last_30d":  scalar(f'{base} |> range(start: -31d) |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> sum()'),
                    "last_365d": scalar(f'{base} |> range(start: -366d) |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> sum()'),
                    "avg_per_month": scalar(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> aggregateWindow(every: 1mo, fn: sum, createEmpty: false) |> mean()'),
                    "avg_per_year":  scalar(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: true) |> aggregateWindow(every: 1y, fn: sum, createEmpty: false) |> mean()'),
                }

            elif meta.meter_type == MeterType.STORAGE:
                stats = {
                    "current_level": scalar(f'{base} |> last()'),
                    "total_refilled": scalar(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value > 0) |> sum()'),
                    "total_consumed": scalar(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value < 0) |> map(fn: (r) => ({{ r with _value: r._value * -1.0 }})) |> sum()'),
                    "avg_consumed_per_month": scalar(f'{base} |> sort(columns: ["_time"]) |> difference(nonNegative: false) |> filter(fn: (r) => r._value < 0) |> map(fn: (r) => ({{ r with _value: r._value * -1.0 }})) |> aggregateWindow(every: 1mo, fn: sum, createEmpty: false) |> mean()'),
                }

            else:  # sensor
                stats = {
                    "last":  scalar(f'{base} |> last()'),
                    "min":   scalar(f'{base} |> min()'),
                    "max":   scalar(f'{base} |> max()'),
                    "mean":  scalar(f'{base} |> mean()'),
                }

    except Exception as e:
        logger.error(f"Stats error for {meter}: {e}")
        return error("query_error", "Failed to compute stats", 502)

    return ok(stats, meta={"meter": meter, "meter_type": meta.meter_type.value, "unit": meta.unit})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve
    logger.info("Starting Consumo API on port 8200")
    serve(app, host="0.0.0.0", port=8200)
