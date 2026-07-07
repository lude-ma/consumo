"""
scheduler.py — Consumo reminder service.

Reads config/reminders.yml and schedules notifications via ntfy.
Runs as a standalone container on the NAS alongside the main stack.
"""

from __future__ import annotations
import logging
import os
import re
import sys
from pathlib import Path

import httpx
import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reminders")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _resolve_env(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""
    def replacer(m):
        key = m.group(1)
        val = os.environ.get(key)
        if val is None:
            logger.warning(f"Environment variable '{key}' is not set")
            return m.group(0)
        return val
    return re.sub(r"\$\{([^}]+)\}", replacer, value)


def load_config() -> dict:
    path = Path(os.environ.get("CONSUMO_REMINDERS_PATH", "/config/reminders.yml"))
    if not path.exists():
        # Dev fallback
        path = Path(__file__).parent.parent.parent / "config" / "reminders.yml"
    if not path.exists():
        logger.error(f"reminders.yml not found at {path}")
        sys.exit(1)

    with open(path) as f:
        raw = f.read()

    # Resolve ${VAR} placeholders before YAML parsing
    resolved = _resolve_env(raw)
    cfg = yaml.safe_load(resolved)
    logger.info(f"Loaded config from {path}")
    return cfg


# ---------------------------------------------------------------------------
# Notification channels
# ---------------------------------------------------------------------------

def send_ntfy(cfg: dict, reminder: dict) -> None:
    """Send a push notification via ntfy."""
    ntfy_cfg = cfg.get("ntfy", {})
    base_url  = ntfy_cfg.get("url", "").rstrip("/")
    channel   = ntfy_cfg.get("channel", "consumo")
    priority  = ntfy_cfg.get("priority", "default")
    tags      = ntfy_cfg.get("tags", ["bell"])
    token     = ntfy_cfg.get("token")

    if not base_url:
        logger.error("ntfy.url is not configured")
        return

    url = f"{base_url}/{channel}"
    headers = {
        "Title":    reminder["name"],
        "Priority": priority,
        "Tags":     ",".join(tags),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.post(
            url,
            content=reminder["message"].encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"Sent ntfy notification: '{reminder['name']}'")
    except httpx.HTTPStatusError as e:
        logger.error(f"ntfy HTTP error: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"ntfy request error: {e}")


CHANNEL_HANDLERS = {
    "ntfy": send_ntfy,
}


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def fire_reminder(cfg: dict, reminder: dict) -> None:
    logger.info(f"Firing reminder: '{reminder['name']}'")
    for channel in reminder.get("channels", []):
        handler = CHANNEL_HANDLERS.get(channel)
        if handler:
            handler(cfg, reminder)
        else:
            logger.warning(f"Unknown channel '{channel}' — skipping")


def setup_scheduler(cfg: dict) -> BlockingScheduler:
    tz = os.environ.get("TZ", "Europe/Berlin")
    scheduler = BlockingScheduler(timezone=tz)

    reminders = cfg.get("reminders", [])
    if not reminders:
        logger.warning("No reminders configured — scheduler will idle")

    for reminder in reminders:
        name     = reminder.get("name", "Unnamed")
        schedule = reminder.get("schedule")

        if not schedule:
            logger.warning(f"Reminder '{name}' has no schedule — skipping")
            continue

        try:
            trigger = CronTrigger.from_crontab(schedule)
        except ValueError as e:
            logger.error(f"Invalid cron expression for '{name}': {schedule} — {e}")
            continue

        scheduler.add_job(
            fire_reminder,
            trigger=trigger,
            args=[cfg, reminder],
            name=name,
            id=name,
            replace_existing=True,
            misfire_grace_time=3600,  # fire up to 1h late if container was down
        )
        logger.info(f"Scheduled '{name}' → {schedule}")

    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logger.info("Consumo reminder service starting...")
    cfg = load_config()

    scheduler = setup_scheduler(cfg)

    logger.info(f"Scheduled {len(scheduler.get_jobs())} reminder(s) — next run times shown after start")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
