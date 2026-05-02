import json
import os
import re
from datetime import datetime, date
from typing import Any

from .constants import DATA_DIR, CONFIG_FILE
from . import logger

_DEFAULTS: dict[str, Any] = {
    "calendar_link": "",
    "calendar_id": "",
    "monitor_start_date": "",
    "monitor_end_date": "",
    "check_interval_minutes": 2,
    "alert_email": "",       # address that receives alerts
    "last_updated": "",
}


def load() -> dict[str, Any]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        return dict(_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
        return merged
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(f"Failed to load config: {exc}")
        return dict(_DEFAULTS)


def save(cfg: dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg["last_updated"] = datetime.utcnow().isoformat() + "Z"
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        logger.info("Configuration saved.")
    except OSError as exc:
        logger.error(f"Failed to save config: {exc}")
        raise


def extract_calendar_id(link: str) -> str:
    """
    Extract calendar ID from any Google Calendar share URL format.
    Supports ?cid= (base64), ?src=, and raw IDs.
    """
    link = link.strip()

    if "@" in link and "http" not in link:
        return link

    cid_match = re.search(r"[?&]cid=([^&]+)", link)
    if cid_match:
        import base64
        try:
            decoded = base64.b64decode(cid_match.group(1) + "==").decode("utf-8")
            if "@" in decoded:
                return decoded
        except Exception:
            pass

    src_match = re.search(r"[?&]src=([^&]+)", link)
    if src_match:
        from urllib.parse import unquote
        return unquote(src_match.group(1))

    raise ValueError(
        "Could not extract a calendar ID from the provided link. "
        "Paste the full Google Calendar share link."
    )


def validate(cfg: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not cfg.get("calendar_link", "").strip():
        errors.append("Calendar link is required.")
    else:
        try:
            extract_calendar_id(cfg["calendar_link"])
        except ValueError as exc:
            errors.append(str(exc))

    for field, label in [
        ("monitor_start_date", "Start date"),
        ("monitor_end_date", "End date"),
    ]:
        val = cfg.get(field, "").strip()
        if not val:
            errors.append(f"{label} is required.")
        else:
            try:
                date.fromisoformat(val)
            except ValueError:
                errors.append(f"{label} must be in YYYY-MM-DD format.")

    if not errors:
        start = cfg.get("monitor_start_date", "")
        end = cfg.get("monitor_end_date", "")
        if start and end and start > end:
            errors.append("Start date must be before end date.")

    interval = cfg.get("check_interval_minutes", 2)
    try:
        if not (1 <= int(interval) <= 60):
            errors.append("Check interval must be between 1 and 60 minutes.")
    except (TypeError, ValueError):
        errors.append("Check interval must be a number.")

    email = cfg.get("alert_email", "").strip()
    if not email:
        errors.append("Alert email address is required.")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Alert email address appears invalid.")

    return errors
