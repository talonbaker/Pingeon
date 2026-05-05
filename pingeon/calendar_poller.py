"""
Polls Google's Appointment Scheduling API for the set of available slots
inside the user's preferred date range and returns them as dates.

Endpoint: calendar-pa.clients6.google.com /$rpc .../ListAvailableSlots
Authentication: public API key embedded in the booking page (no user creds).
The API caps each request at ~30 days, so we paginate.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .constants import (
    APPT_API_URL, APPT_API_KEY, APPT_WINDOW_DAYS,
    FETCH_TIMEOUT_SECONDS, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS,
)
from . import logger


def _post(schedule_id: str, start_ts: int, end_ts: int) -> Any:
    body = json.dumps([None, None, schedule_id, None, [[start_ts], [end_ts]]]).encode("utf-8")
    req = urllib.request.Request(
        APPT_API_URL,
        data=body,
        headers={
            "X-Goog-Api-Key": APPT_API_KEY,
            "Content-Type": "application/json+protobuf",
            "X-User-Agent": "grpc-web-javascript/0.1",
            "Origin": "https://calendar.google.com",
            "Referer": "https://calendar.google.com/",
            "User-Agent": "Pingeon/1.0",
        },
        method="POST",
    )
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Slot API HTTP {exc.code}: {detail}")
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Slot fetch attempt {attempt} failed: {exc}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"Slot API failed after {RETRY_ATTEMPTS} attempts: {last_exc}")


def _harvest_timestamps(node: Any, out: list[int]) -> None:
    """Recursively collect plausible Unix-second timestamps from the response."""
    if isinstance(node, list):
        if len(node) == 1:
            val = node[0]
            if isinstance(val, str):
                try:
                    val = int(val)
                except ValueError:
                    pass
            if isinstance(val, int) and 1_600_000_000 <= val <= 2_500_000_000:
                out.append(val)
                return
        for child in node:
            _harvest_timestamps(child, out)
    elif isinstance(node, dict):
        for v in node.values():
            _harvest_timestamps(v, out)


def _slots_to_dates(payload: Any) -> set[date]:
    """Convert ListAvailableSlots response → set of UTC-day calendar dates.

    The response is a nested JSON array. Each available slot has its start time
    encoded as [unix_seconds] somewhere in its sub-tree. We collect every such
    timestamp and reduce to the day. Two timestamps belong to the same slot
    (start + end), so we de-dupe by date.
    """
    timestamps: list[int] = []
    _harvest_timestamps(payload, timestamps)
    return {datetime.fromtimestamp(ts, tz=timezone.utc).date() for ts in timestamps}


def _windowed(start_date: date, end_date: date, span_days: int):
    cur = start_date
    while cur <= end_date:
        win_end = min(cur + timedelta(days=span_days), end_date + timedelta(days=1))
        yield cur, win_end
        cur = win_end


def _fetch_available_dates_appointment(
    schedule_id: str, start_date: date, end_date: date
) -> set[date]:
    """Return every date in [start_date, end_date] that has at least one bookable slot."""
    available: set[date] = set()
    for win_start, win_end in _windowed(start_date, end_date, APPT_WINDOW_DAYS):
        st = int(datetime(win_start.year, win_start.month, win_start.day, tzinfo=timezone.utc).timestamp())
        en = int(datetime(win_end.year, win_end.month, win_end.day, tzinfo=timezone.utc).timestamp())
        try:
            payload = _post(schedule_id, st, en)
        except Exception as exc:
            logger.error(f"Window {win_start}..{win_end} fetch failed: {exc}")
            continue
        logger.debug(f"Raw API response: {json.dumps(payload)[:500]}")
        dates = _slots_to_dates(payload)
        in_range = {d for d in dates if start_date <= d <= end_date}
        logger.debug(f"Window {win_start}..{win_end}: {len(in_range)} day(s) available.")
        available.update(in_range)
    return available


def _build_ics_url(calendar_id: str) -> str:
    if calendar_id.startswith("http"):
        return calendar_id
    return (
        "https://calendar.google.com/calendar/ical/"
        f"{urllib.parse.quote(calendar_id, safe='')}/public/basic.ics"
    )


def _fetch_ics(ics_url: str) -> str:
    req = urllib.request.Request(ics_url, headers={"User-Agent": "Pingeon/1.0"})
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"ICS fetch HTTP {exc.code} — calendar may not be set to public"
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(f"ICS fetch attempt {attempt} failed: {exc}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"ICS fetch failed after {RETRY_ATTEMPTS} attempts: {last_exc}")


def _parse_ics_date(value: str) -> Optional[date]:
    s = value.strip()[:8]
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def _parse_ics_busy_dates(ics_text: str, start_date: date, end_date: date) -> set[date]:
    """Return every date in [start_date, end_date] that has at least one event."""
    busy: set[date] = set()
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_text)
    in_event = False
    ev_start: Optional[date] = None
    ev_end: Optional[date] = None
    for line in unfolded.splitlines():
        key = line.split(":", 1)[0].split(";")[0].upper()
        val = line.split(":", 1)[1] if ":" in line else ""
        if key == "BEGIN" and val.strip() == "VEVENT":
            in_event, ev_start, ev_end = True, None, None
        elif key == "END" and val.strip() == "VEVENT":
            if in_event and ev_start:
                end = ev_end if ev_end else ev_start + timedelta(days=1)
                d = ev_start
                while d < end:
                    if start_date <= d <= end_date:
                        busy.add(d)
                    d += timedelta(days=1)
            in_event = False
        elif in_event:
            if key == "DTSTART":
                ev_start = _parse_ics_date(val)
            elif key == "DTEND":
                ev_end = _parse_ics_date(val)
    return busy


def _fetch_available_dates_ics(
    calendar_id: str, start_date: date, end_date: date
) -> set[date]:
    """Return dates in [start_date, end_date] that have no events (free days)."""
    ics_url = _build_ics_url(calendar_id)
    logger.debug(f"Fetching ICS: {ics_url}")
    ics_text = _fetch_ics(ics_url)
    busy = _parse_ics_busy_dates(ics_text, start_date, end_date)
    free = all_days_in_range(start_date, end_date) - busy
    logger.debug(f"ICS: {len(busy)} busy, {len(free)} free in range.")
    return free


def fetch_available_dates(
    calendar_id: str,
    start_date: date,
    end_date: date,
    calendar_type: str = "appointment",
) -> set[date]:
    if calendar_type == "ics":
        return _fetch_available_dates_ics(calendar_id, start_date, end_date)
    return _fetch_available_dates_appointment(calendar_id, start_date, end_date)


def all_days_in_range(start_date: date, end_date: date) -> set[date]:
    days: set[date] = set()
    day = start_date
    while day <= end_date:
        days.add(day)
        day += timedelta(days=1)
    return days
