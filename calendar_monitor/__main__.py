"""
Entry point for the Photographer Monitor application.

  python -m photographer_monitor          → launch GUI
  python -m photographer_monitor --poll   → run one poll cycle (CLI / task use)
"""

import argparse
import sys
from datetime import date

from . import config, logger
from .calendar_poller import fetch_and_diff


def _poll_once() -> None:
    cfg = config.load()
    errors = config.validate(cfg)
    if errors:
        for e in errors:
            print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    calendar_id = cfg["calendar_id"]
    start_date = date.fromisoformat(cfg["monitor_start_date"])
    end_date = date.fromisoformat(cfg["monitor_end_date"])

    logger.info("Manual poll started.")
    cancelled = fetch_and_diff(calendar_id, start_date, end_date)

    if cancelled:
        print(f"Cancellation(s) detected: {[e.label() for e in cancelled]}")
        logger.info(f"{len(cancelled)} cancellation(s) detected on manual poll.")
    else:
        print("No cancellations detected.")
    logger.info("Manual poll complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Photographer Monitor")
    parser.add_argument(
        "--poll", action="store_true",
        help="Run a single poll cycle and exit (no GUI, no email).",
    )
    args = parser.parse_args()

    if args.poll:
        _poll_once()
    else:
        from .gui import run
        run()


if __name__ == "__main__":
    main()
