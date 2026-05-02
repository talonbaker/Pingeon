"""
Fetches a public Google Calendar ICS feed and diffs it against the last
known state to detect newly available slots (cancellations).

External connection: Google Calendar ICS feed only — read-only, no auth.
"""

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import urllib.request

from icalendar import Calendar  # type: ignore

from .constants import (
    DATA_DIR, DB_FILE, ICS_URL_TEMPLATE,
    FETCH_TIMEOUT_SECONDS, RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS,
)
from . import logger

os.makedirs(DATA_DIR, exist_ok=True)


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    start: date
    end: date

    def label(self) -> str:
        return f"{self.summary} on {self.start}"


def _fetch_ics(calendar_id: str) -> bytes:
    url = ICS_URL_TEMPLATE.format(calendar_id=calendar_id)
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.debug(f"Fetching ICS (attempt {attempt})")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Pingeon/1.0 (public-calendar-read)"},
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


def _load_previous_uids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT uid FROM calendar_state").fetchall()}


def _load_event_details(conn: sqlite3.Connection, uids: set[str]) -> list[CalendarEvent]:
    results: list[CalendarEvent] = []
    for uid in uids:
        row = conn.execute(
            "SELECT uid, summary, start_date, end_date FROM calendar_state WHERE uid = ?",
            (uid,),
        ).fetchone()
        if row:
            results.append(CalendarEvent(
                uid=row[0], summary=row[1],
                start=date.fromisoformat(row[2]),
                end=date.fromisoformat(row[3]),
            ))
    return results


def _save_state(conn: sqlite3.Connection, events: list[CalendarEvent]) -> None:
    conn.execute("DELETE FROM calendar_state")
    conn.executemany(
        "INSERT INTO calendar_state (uid, summary, start_date, end_date) VALUES (?, ?, ?, ?)",
        [(e.uid, e.summary, e.start.isoformat(), e.end.isoformat()) for e in events],
    )
    conn.commit()


def fetch_and_diff(
    calendar_id: str, start_date: date, end_date: date
) -> list[CalendarEvent]:
    """
    Return events that disappeared since the last check (newly open slots).
    First run establishes baseline — no alerts sent.
    """
    raw = _fetch_ics(calendar_id)
    current_events = _parse_ics(raw, start_date, end_date)
    current_uids = {e.uid for e in current_events}

    conn = _get_db()
    previous_uids = _load_previous_uids(conn)

    if not previous_uids:
        logger.info(f"Baseline established: {len(current_events)} event(s) in range.")
        _save_state(conn, current_events)
        conn.close()
        return []

    cancelled_uids = previous_uids - current_uids
    cancelled = _load_event_details(conn, cancelled_uids)

    _save_state(conn, current_events)
    conn.close()

    if cancelled:
        logger.info(f"Opening(s) detected: {', '.join(e.label() for e in cancelled)}")
    else:
        logger.debug("No changes detected.")

    return cancelled
