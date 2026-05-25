#!/usr/bin/env python3
"""
build_dashboards.py
Renders dashboard_template.json for each language in apps/web/i18n/
and writes the result to grafana/dashboards/energy_{lang}.json.

Usage:
    python infrastructure/grafana/build_dashboards.py

    # or via Makefile:
    make build-dashboards
"""

import json
import re
import sys
from pathlib import Path

ROOT          = Path(__file__).parent.parent.parent
TEMPLATE_FILE = Path(__file__).parent / "dashboard_template.json"
I18N_DIR      = ROOT / "apps" / "web" / "i18n"
OUTPUT_DIR    = Path(__file__).parent / "dashboards"


def render(template: str, t: dict) -> str:
    """Replace all {{t.key}} placeholders with values from the translation dict."""
    def replacer(match):
        key = match.group(1)
        if key not in t:
            print(f"  WARNING: missing key '{key}'", file=sys.stderr)
            return match.group(0)  # leave placeholder intact
        # Escape for JSON string context
        return t[key].replace("\\", "\\\\").replace('"', '\\"')

    return re.sub(r"\{\{t\.([^}]+)\}\}", replacer, template)


def build():
    if not TEMPLATE_FILE.exists():
        print(f"ERROR: Template not found at {TEMPLATE_FILE}", file=sys.stderr)
        sys.exit(1)

    template = TEMPLATE_FILE.read_text("utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lang_files = sorted(I18N_DIR.glob("*.json"))
    if not lang_files:
        print(f"ERROR: No language files found in {I18N_DIR}", file=sys.stderr)
        sys.exit(1)

    for lang_file in lang_files:
        lang = lang_file.stem
        t    = json.loads(lang_file.read_text("utf-8"))

        rendered = render(template, t)

        # Validate the result is valid JSON
        try:
            parsed = json.loads(rendered)
        except json.JSONDecodeError as e:
            print(f"ERROR: Rendered dashboard for '{lang}' is not valid JSON: {e}",
                  file=sys.stderr)
            sys.exit(1)

        # Stamp the lang into the dashboard uid so both can be provisioned
        parsed["uid"]   = f"energy-{lang}"
        parsed["title"] = t.get("grafana_dashboard_title", parsed.get("title", ""))

        out = OUTPUT_DIR / f"energy_{lang}.json"
        out.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
        print(f"  ✓  {lang:6}  →  {out.relative_to(ROOT)}")

    print(f"\nBuilt {len(lang_files)} dashboard(s).")


if __name__ == "__main__":
    print("Building Grafana dashboards from template...\n")
    build()
