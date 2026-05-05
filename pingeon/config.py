import base64
import json
import os
import re
import urllib.request
from datetime import datetime, date
from typing import Any
from urllib.parse import unquote, urlparse

from .constants import DATA_DIR, CONFIG_FILE
from . import logger

_DEFAULTS: dict[str, Any] = {
    "calendar_link": "",
    "calendar_id": "",
    "calendar_type": "",     # "appointment" or "ics"
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


def _resolve_google_short_link(link: str) -> str:
    """Follow redirects on a calendar.app.google short link.
    Caller must verify hostname before calling -- never invoke with
    arbitrary user-supplied URLs (SSRF)."""
    req = urllib.request.Request(link, headers={"User-Agent": "Pingeon/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.geturl()


def extract_calendar_id(link: str) -> str:
    """
    Extract a polling identifier from any Google Calendar share URL format.
    Returns a raw appointment schedule ID (starts with 'AcZssZ...') for
    appointment-scheduling links, otherwise a calendar ID for ICS-style ones.
    """
    link = link.strip()

    # Raw appointment schedule IDs as pasted by the user.
    if link.startswith("AcZssZ") and "/" not in link and "?" not in link:
        return link

    if "@" in link and "http" not in link:
        return link

    # Direct ICS / webcal URL.
    if link.startswith("webcal://"):
        return "https://" + link[len("webcal://"):]
    if re.search(r"\.ics($|\?)", link) and link.startswith("http"):
        return link

    # Short link -- resolve via HTTP redirect, then recurse on the long URL.
    # Strict hostname check (parsed, not substring) keeps this from being
    # an SSRF gadget for arbitrary user input.
    parsed = urlparse(link)
    if parsed.hostname == "calendar.app.google":
        try:
            resolved = _resolve_google_short_link(link)
        except Exception as exc:
            raise ValueError(
                "Could not resolve the calendar.app.google short link. "
                "Open it in a browser and paste the long URL from the "
                f"address bar instead. ({exc})"
            )
        if resolved and resolved != link:
            return extract_calendar_id(resolved)

    appt_match = re.search(r"/appointments/schedules/([A-Za-z0-9_-]+)", link)
    if appt_match:
        return appt_match.group(1)

    cid_match = re.search(r"[?&]cid=([^&]+)", link)
    if cid_match:
        cid = cid_match.group(1)
        for decoder in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                decoded = decoder(cid + "==").decode("utf-8")
                if "@" in decoded:
                    return decoded
            except Exception:
                pass

    src_match = re.search(r"[?&]src=([^&]+)", link)
    if src_match:
        return unquote(src_match.group(1))

    ical_match = re.search(r"/calendar/ical/([^/]+)/", link)
    if ical_match:
        return unquote(ical_match.group(1))

    raise ValueError(
        "Could not extract a calendar ID from the provided link. "
        "Open the calendar in a browser and paste the URL from the address bar."
    )


def detect_calendar_type(calendar_id: str) -> str:
    """Return 'ics' for regular calendars, 'appointment' for scheduling links."""
    if "@" in calendar_id or calendar_id.startswith("http"):
        return "ics"
    return "appointment"


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
