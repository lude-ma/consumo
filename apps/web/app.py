import os
import json
import logging
import requests as http
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, make_response

from consumo_common.models import METERS, METER_TYPE_ICONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

API_URL = os.environ.get("API_URL", "http://localhost:8200")
API_KEY = os.environ.get("API_KEY", "")

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

I18N_DIR     = Path(__file__).parent / "i18n"
SUPPORTED    = ["en", "de"]
DEFAULT_LANG = "en"
_translations: dict[str, dict] = {}

def _load_translations():
    for lang in SUPPORTED:
        path = I18N_DIR / f"{lang}.json"
        if path.exists():
            _translations[lang] = json.loads(path.read_text("utf-8"))
        else:
            logger.warning(f"Missing translation file: {path}")

_load_translations()


def _detect_lang() -> str:
    """Cookie > Accept-Language header > default."""
    # 1. Explicit cookie (set by language switcher)
    lang = request.cookies.get("lang")
    if lang in SUPPORTED:
        return lang
    # 2. Browser preference
    accept = request.headers.get("Accept-Language", "")
    for part in accept.replace(" ", "").split(","):
        code = part.split(";")[0].split("-")[0].lower()
        if code in SUPPORTED:
            return code
    return DEFAULT_LANG


def get_t() -> dict:
    return _translations.get(_detect_lang(), _translations[DEFAULT_LANG])


@app.route("/set-lang/<lang>")
def set_lang(lang: str):
    """Language switcher — sets cookie and redirects back."""
    referrer = request.referrer or url_for("index")
    if lang not in SUPPORTED:
        return redirect(referrer)
    resp = make_response(redirect(referrer))
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


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
    t = get_t()
    return render_template("index.html", meters=METERS,
                           type_icons=METER_TYPE_ICONS, t=t,
                           supported_langs=SUPPORTED, current_lang=_detect_lang())


@app.route("/enter/<meter>", methods=["GET", "POST"])
def enter(meter: str):
    t = get_t()
    if meter not in METERS:
        flash(t["flash_unknown_meter"], "error")
        return redirect(url_for("index"))

    meta = METERS[meter]
    last_reading = None

    try:
        rows = api("GET", f"/api/v1/meters/{meter}/readings",
                   params={"limit": 1, "order": "desc"}).get("data", [])
        if rows:
            last_reading = rows[0]
    except Exception:
        pass

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
            flash(t["flash_saved"].format(label=t[f"meter_{meter}_label"], value=value, unit=meta.unit), "success")
            return redirect(url_for("history", meter=meter))

        except ValueError:
            flash(t["flash_invalid_value"], "error")
        except http.exceptions.HTTPError as e:
            body = e.response.json() if e.response else {}
            flash(t["flash_api_error"].format(message=body.get("message", str(e))), "error")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            flash(t["flash_api_error"].format(message=str(e)), "error")

    return render_template("enter.html", meter=meter, meta=meta,
                           last_reading=last_reading,
                           type_icons=METER_TYPE_ICONS, t=t,
                           supported_langs=SUPPORTED, current_lang=_detect_lang())


@app.route("/history/<meter>")
def history(meter: str):
    t = get_t()
    if meter not in METERS:
        flash(t["flash_unknown_meter"], "error")
        return redirect(url_for("index"))

    meta  = METERS[meter]
    rows  = []
    stats = None

    try:
        rows  = api("GET", f"/api/v1/meters/{meter}/readings",
                    params={"limit": 20, "order": "desc"}).get("data", [])
        stats = api("GET", f"/api/v1/meters/{meter}/stats").get("data", {})
    except http.exceptions.HTTPError as e:
        body = e.response.json() if e.response else {}
        flash(t["flash_api_error"].format(message=body.get("message", str(e))), "error")
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        flash(t["flash_load_error"], "error")

    return render_template("history.html", meter=meter, meta=meta,
                           rows=rows, stats=stats,
                           type_icons=METER_TYPE_ICONS, t=t,
                           supported_langs=SUPPORTED, current_lang=_detect_lang())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from waitress import serve
    logger.info("Starting Consumo Web on port 8100")
    serve(app, host="0.0.0.0", port=8100)
