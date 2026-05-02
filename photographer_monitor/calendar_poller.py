"""
Fetches and diffs a photographer's public Google Calendar ICS feed.

External connection: Google Calendar ICS feed (read-only, no auth required).
Nothing else leaves the machine from this module.
"""

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import urllib.request

from icalendar import Calendar  # type: ignore

from .constants import (
    DB_FILE, DATA_DIR, ICS_URL_TEMPLATE,
    FETCH_TIMEOUT_SECONDS, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS,
)
from . import logger

import os
os.makedirs(DATA_DIR, exist_ok=True)


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    start: date
    end: date

    def label(self) -> str:
        return f"{self.summary} on {self.start}"


def _ics_url(calendar_id: str) -> str:
    return ICS_URL_TEMPLATE.format(calendar_id=calendar_id)


def _fetch_ics(calendar_id: str) -> bytes:
    """Fetch raw ICS bytes from Google Calendar. Retries on transient failures."""
    url = _ics_url(calendar_id)
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.debug(f"Fetching ICS (attempt {attempt}): {url}")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PhotographerMonitor/1.0 (public-calendar-read)"},
            )
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
                return resp.read()
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Fetch attempt {attempt} failed: {exc}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"Calendar fetch failed after {RETRY_ATTEMPTS} attempts: {last_exc}")


def _parse_ics(raw: bytes, start_date: date, end_date: date) -> list[CalendarEvent]:
    """Parse an ICS byte string and return events within [start_date, end_date]."""
    events: list[CalendarEvent] = []
    try:
        cal = Calendar.from_ical(raw)
    except Exception as exc:
        logger.error(f"ICS parse error: {exc}")
        return events

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        try:
            uid = str(component.get("UID", ""))
            summary = str(component.get("SUMMARY", "Busy"))
            dtstart = component.get("DTSTART")
            dtend = component.get("DTEND")

            if dtstart is None:
                continue

            ev_start = dtstart.dt
            ev_end = dtend.dt if dtend else ev_start

            # Normalise datetime → date for comparison
            if isinstance(ev_start, datetime):
                ev_start = ev_start.date()
            if isinstance(ev_end, datetime):
                ev_end = ev_end.date()

            if ev_end < start_date or ev_start > end_date:
                continue

            events.append(CalendarEvent(uid=uid, summary=summary, start=ev_start, end=ev_end))
        except Exception as exc:
            logger.warning(f"Skipping malformed VEVENT: {exc}")

    return events


# --- State persistence (SQLite) ---

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS calendar_state (
            uid TEXT PRIMARY KEY,
            summary TEXT,
            start_date TEXT,
            end_date TEXT
        )"""
    )
    conn.commit()
    return conn


def _load_previous_state(conn: sqlite3.Connection) -> set[str]:
    """Return the set of UIDs that were present in the last snapshot."""
    rows = conn.execute("SELECT uid FROM calendar_state").fetchall()
    return {row[0] for row in rows}


def _save_state(conn: sqlite3.Connection, events: list[CalendarEvent]) -> None:
    conn.execute("DELETE FROM calendar_state")
    conn.executemany(
        "INSERT INTO calendar_state (uid, summary, start_date, end_date) VALUES (?, ?, ?, ?)",
        [(e.uid, e.summary, e.start.isoformat(), e.end.isoformat()) for e in events],
    )
    conn.commit()


def _load_event_details(conn: sqlite3.Connection, uids: set[str]) -> list[CalendarEvent]:
    """Retrieve full CalendarEvent rows from the previous state for the given UIDs."""
    results: list[CalendarEvent] = []
    for uid in uids:
        row = conn.execute(
            "SELECT uid, summary, start_date, end_date FROM calendar_state WHERE uid = ?",
            (uid,),
        ).fetchone()
        if row:
            results.append(
                CalendarEvent(
                    uid=row[0],
                    summary=row[1],
                    start=date.fromisoformat(row[2]),
                    end=date.fromisoformat(row[3]),
                )
            )
    return results


def fetch_and_diff(
    calendar_id: str, start_date: date, end_date: date
) -> list[CalendarEvent]:
    """
    Fetch current calendar events, compare to last known state, and return
    events that have disappeared (i.e. cancellations / newly-open slots).

    On the very first run there is no previous state, so no diff is returned —
    this prevents a flood of false-positive alerts on first launch.
    """
    raw = _fetch_ics(calendar_id)
    current_events = _parse_ics(raw, start_date, end_date)
    current_uids = {e.uid for e in current_events}

    conn = _get_db()
    previous_uids = _load_previous_state(conn)

    if not previous_uids:
        # First run — establish baseline, no alerts
        logger.info(
            f"Baseline established: {len(current_events)} event(s) in monitored range."
        )
        _save_state(conn, current_events)
        conn.close()
        return []

    cancelled_uids = previous_uids - current_uids
    cancelled_events = _load_event_details(conn, cancelled_uids)

    _save_state(conn, current_events)
    conn.close()

    if cancelled_events:
        labels = ", ".join(e.label() for e in cancelled_events)
        logger.info(f"Cancellation(s) detected: {labels}")
    else:
        logger.debug("No cancellations detected.")

    return cancelled_events
