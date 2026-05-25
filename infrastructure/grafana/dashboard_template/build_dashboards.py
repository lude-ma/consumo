#!/usr/bin/env python3
"""
build_dashboards.py
Renders dashboard_template.json for each language in apps/web/i18n/
and writes the result to grafana/dashboards/consumo_{lang}.json.

Usage (run from repo root or deploy/):
    python infrastructure/grafana/build_dashboards.py
    python infrastructure/grafana/build_dashboards.py --env deploy/.env.prod

    # or via Makefile:
    make build-dashboards
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT          = Path(__file__).parent.parent.parent.parent
TEMPLATE_FILE = Path(__file__).parent / "dashboard_template.json"
I18N_DIR      = ROOT / "apps" / "web" / "i18n"
OUTPUT_DIR    = Path(__file__).parent.parent / "dashboards"


# ---------------------------------------------------------------------------
# .env loader — no external dependencies
# ---------------------------------------------------------------------------

def load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_i18n(template: str, t: dict) -> str:
    """Replace {{t.key}} placeholders with translated strings."""
    def replacer(match):
        key = match.group(1)
        if key not in t:
            print(f"  WARNING: missing i18n key '{key}'", file=sys.stderr)
            return match.group(0)  # leave placeholder intact
        # Escape for JSON string context
        return t[key].replace("\\", "\\\\").replace('"', '\\"')

    return re.sub(r"\{\{t\.([^}]+)\}\}", replacer, template)


def render_env(template: str, env: dict[str, str]) -> str:
    """Replace ${VAR} placeholders with values from env dict."""
    def replacer(match):
        key = match.group(1)
        val = env.get(key) or os.environ.get(key)
        if val is None:
            print(f"  WARNING: missing env var '{key}' — keeping placeholder", file=sys.stderr)
            return match.group(0)
        return val

    return re.sub(r"\$\{([^}]+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(env_file: Path | None = None):
    if not TEMPLATE_FILE.exists():
        print(f"ERROR: Template not found at {TEMPLATE_FILE}", file=sys.stderr)
        sys.exit(1)

    # Load env vars for ${VAR} substitution
    env: dict[str, str] = {}
    if env_file:
        env_file = Path(os.getcwd()) / env_file if not env_file.is_absolute() else env_file
    if env_file and env_file.exists():
        env = load_env_file(env_file)
        print(f"Loaded env from {env_file.resolve()}")
    else:
        # Try default locations
        for candidate in [ROOT / "deploy" / ".env.prod", ROOT / "deploy" / ".env.dev"]:
            if candidate.exists():
                env = load_env_file(candidate)
                print(f"Loaded env from {candidate.resolve()}")
                break
        else:
            print("No .env file found — will use environment variables for ${VAR} substitution")

    template = TEMPLATE_FILE.read_text("utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lang_files = sorted(I18N_DIR.glob("*.json"))
    if not lang_files:
        print(f"ERROR: No language files found in {I18N_DIR}", file=sys.stderr)
        sys.exit(1)

    for lang_file in lang_files:
        lang = lang_file.stem
        t    = json.loads(lang_file.read_text("utf-8"))

        # 1. Substitute i18n strings
        rendered = render_i18n(template, t)

        # 2. Substitute env vars (e.g. ${INFLUXDB_BUCKET})
        rendered = render_env(rendered, env)

        # 3. Validate JSON
        try:
            parsed = json.loads(rendered)
        except json.JSONDecodeError as e:
            print(f"ERROR: Rendered dashboard for '{lang}' is not valid JSON: {e}",
                  file=sys.stderr)
            sys.exit(1)

        # 4. Stamp uid and title
        parsed["uid"]   = f"consumo-{lang}"
        parsed["title"] = t.get("grafana_dashboard_title", parsed.get("title", ""))

        out = OUTPUT_DIR / f"consumo_{lang}.json"
        out.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
        print(f"  ✓  {lang:6}  →  {out.relative_to(ROOT)}")

    print(f"\nBuilt {len(lang_files)} dashboard(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Grafana dashboards from template")
    parser.add_argument("--env", type=Path, default=None,
                        help="Path to .env file (default: deploy/.env.prod)")
    args = parser.parse_args()

    print("Building Grafana dashboards from template...\n")
    build(env_file=args.env)
