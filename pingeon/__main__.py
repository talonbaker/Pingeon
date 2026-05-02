"""
python -m pingeon          → launch GUI
python -m pingeon --poll   → single poll cycle (no GUI, no notifications)
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

    logger.info("Manual poll started.")
    opened = fetch_and_diff(
        cfg["calendar_id"],
        date.fromisoformat(cfg["monitor_start_date"]),
        date.fromisoformat(cfg["monitor_end_date"]),
    )
    print(f"Openings detected: {[e.label() for e in opened]}" if opened else "No changes.")
    logger.info("Manual poll complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pingeon — Calendar Monitor")
    parser.add_argument("--poll", action="store_true",
                        help="Run one poll cycle and exit (no GUI, no alerts).")
    args = parser.parse_args()

    if args.poll:
        _poll_once()
    else:
        from .gui import run
        run()


if __name__ == "__main__":
    main()
