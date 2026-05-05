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
from datetime import date

from .constants import NOTIFY_ENDPOINT
from . import logger


def _make_request(url: str, payload: dict) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Pingeon/1.0",
        },
        method="POST",
    )


def send_alert(alert_email: str, available_dates: list[date], kind: str = "update") -> None:
    """POST available dates to the relay Worker, which emails the user.

    kind="initial" -> first-poll snapshot of currently-open dates.
    kind="update"  -> a date just transitioned to available (cancellation).
    """
    if not available_dates:
        return

    payload = {
        "to": alert_email,
        "kind": kind,
        "slots": [{"date": d.isoformat()} for d in sorted(available_dates)],
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
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info(f"Test alert relayed (HTTP {resp.status}).")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Relay HTTP {exc.code}: {detail}") from exc
