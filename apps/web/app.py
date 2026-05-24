import os
import logging
import requests as http
from flask import Flask, render_template, request, redirect, url_for, flash

from consumo_common.models import METERS, METER_TYPE_LABELS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

API_URL = os.environ.get("API_URL", "http://localhost:8200")
API_KEY = os.environ.get("API_KEY", "")


# ---------------------------------------------------------------------------
# API client helper
# ---------------------------------------------------------------------------

def api(method: str, path: str, **kwargs):
    """Thin wrapper around requests — injects auth header, raises on HTTP errors."""
    url = f"{API_URL}{path}"
    headers = {"X-API-Key": API_KEY, **(kwargs.pop("headers", {}))}
    resp = http.request(method, url, headers=headers, timeout=10, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", meters=METERS, type_labels=METER_TYPE_LABELS)


@app.route("/enter/<meter>", methods=["GET", "POST"])
def enter(meter: str):
    if meter not in METERS:
        flash("Unbekannter Zähler.", "error")
        return redirect(url_for("index"))

    meta = METERS[meter]
    last_reading = None

    try:
        rows = api("GET", f"/api/v1/meters/{meter}/readings",
                   params={"limit": 1, "order": "desc"}).get("data", [])
        if rows:
            last_reading = rows[0]
    except Exception:
        pass  # non-critical — form still works without it

    if request.method == "POST":
        try:
            value    = float(request.form["value"].replace(",", "."))
            note     = request.form.get("note", "").strip()
            date_str = request.form.get("date", "").strip()

            payload = {"value": value}
            if note:
                payload["note"] = note
            if date_str:
                # HTML datetime-local → ISO 8601 UTC
                payload["timestamp"] = date_str + ":00Z"

            api("POST", f"/api/v1/meters/{meter}/readings", json=payload)
            flash(f"✓ {meta.label} gespeichert: {value} {meta.unit}", "success")
            return redirect(url_for("history", meter=meter))

        except ValueError:
            flash("Ungültiger Wert — bitte eine Zahl eingeben.", "error")
        except http.exceptions.HTTPError as e:
            body = e.response.json() if e.response else {}
            flash(f"API-Fehler: {body.get('message', str(e))}", "error")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            flash("Unbekannter Fehler beim Speichern.", "error")

    return render_template("enter.html", meter=meter, meta=meta,
                           last_reading=last_reading,
                           type_labels=METER_TYPE_LABELS)


@app.route("/history/<meter>")
def history(meter: str):
    if meter not in METERS:
        flash("Unbekannter Zähler.", "error")
        return redirect(url_for("index"))

    meta   = METERS[meter]
    rows   = []
    stats  = None

    try:
        rows  = api("GET", f"/api/v1/meters/{meter}/readings",
                    params={"limit": 20, "order": "desc"}).get("data", [])
        stats = api("GET", f"/api/v1/meters/{meter}/stats").get("data", {})
    except http.exceptions.HTTPError as e:
        body = e.response.json() if e.response else {}
        flash(f"API-Fehler: {body.get('message', str(e))}", "error")
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        flash("Fehler beim Laden der Daten.", "error")

    return render_template("history.html", meter=meter, meta=meta,
                           rows=rows, stats=stats,
                           type_labels=METER_TYPE_LABELS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve
    logger.info("Starting Consumo Web on port 8100")
    serve(app, host="0.0.0.0", port=8100)
