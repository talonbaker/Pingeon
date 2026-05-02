"""
Alert delivery.

Sends an email to the user-configured address via the Pingeon relay Worker.
No credentials are required from the user — the Worker holds the sending
credentials on the server side.

External connection: POST to the Pingeon Cloudflare Worker /notify endpoint.
"""

import json
import urllib.request
import urllib.error
from typing import TYPE_CHECKING

from .constants import NOTIFY_ENDPOINT, NOTIFY_TOKEN
from . import logger

if TYPE_CHECKING:
    from .calendar_poller import CalendarEvent


def _make_request(url: str, payload: dict) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Pingeon/1.0",
            "Authorization": f"Bearer {NOTIFY_TOKEN}",
        },
        method="POST",
    )


def send_alert(alert_email: str, events: "list[CalendarEvent]") -> None:
    """POST slot info to the relay Worker, which emails the user."""
    if not events:
        return

    payload = {
        "to": alert_email,
        "slots": [
            {"summary": e.summary, "date": e.start.isoformat()}
            for e in events
        ],
    }
    req = _make_request(f"{NOTIFY_ENDPOINT}/notify", payload)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info(f"Alert email relayed (HTTP {resp.status}).")
    except urllib.error.HTTPError as exc:
        logger.error(f"Relay HTTP error: {exc.code} -- {exc.read().decode()}")
        raise
    except Exception as exc:
        logger.error(f"Alert relay failed: {exc}")
        raise


def send_test(alert_email: str) -> None:
    """Send a test alert to verify the email address and relay are working."""
    req = _make_request(f"{NOTIFY_ENDPOINT}/notify", {"to": alert_email, "test": True})
    with urllib.request.urlopen(req, timeout=15) as resp:
        logger.info(f"Test alert relayed (HTTP {resp.status}).")
