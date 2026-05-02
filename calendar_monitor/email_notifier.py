"""
Sends alert emails via Gmail SMTP (TLS).

External connection: smtp.gmail.com:587 — only when an alert or test is triggered.
The password is accepted as a parameter and is NEVER written to disk or logged.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import TYPE_CHECKING

from .constants import SMTP_HOST, SMTP_PORT
from . import logger

if TYPE_CHECKING:
    from .calendar_poller import CalendarEvent


_SUBJECT = "\U0001f4c5 Photographer Availability Alert!"

_BODY_TEMPLATE = """\
Hi there!

A time slot just became available in your desired date range!

\U0001f4c5 Available Date: {date}
⏰ Was scheduled: {summary}

This slot was detected at: {detected_at}

Contact the photographer immediately to claim this spot before someone else does.

---
Photographer Monitor v1.0
Open the app to view monitoring details or stop monitoring.
"""

_TEST_SUBJECT = "✅ Photographer Monitor — Test Email"

_TEST_BODY = """\
Your Photographer Monitor email configuration is working correctly.

You will receive alerts like this one whenever a cancellation is detected
in your monitored date range.

---
Photographer Monitor v1.0
"""


def _build_message(from_addr: str, to_addr: str, subject: str, body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def _send(email: str, password: str, subject: str, body: str) -> None:
    """Low-level send. Password is used only for SMTP AUTH and never logged."""
    msg = _build_message(email, email, subject, body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email, password)  # password only in SMTP AUTH over TLS
        server.sendmail(email, [email], msg.as_string())


def send_alert_email(
    email: str,
    password: str,
    cancelled_events: "list[CalendarEvent]",
) -> None:
    """Send one alert email listing all newly available slots."""
    if not cancelled_events:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bodies: list[str] = []
    for ev in cancelled_events:
        bodies.append(
            _BODY_TEMPLATE.format(
                date=ev.start.isoformat(),
                summary=ev.summary,
                detected_at=now,
            )
        )

    full_body = "\n---\n".join(bodies)
    try:
        _send(email, password, _SUBJECT, full_body)
        logger.info(f"Alert email sent for {len(cancelled_events)} slot(s).")
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check your email and password.")
        raise
    except Exception as exc:
        logger.error(f"Failed to send alert email: {exc}")
        raise


def send_test_email(email: str, password: str) -> None:
    """Send a test email to verify credentials and connectivity."""
    try:
        _send(email, password, _TEST_SUBJECT, _TEST_BODY)
        logger.info("Test email sent successfully.")
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check your email and password.")
        raise
    except Exception as exc:
        logger.error(f"Failed to send test email: {exc}")
        raise
