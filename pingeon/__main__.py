"""
python -m pingeon          → launch GUI
python -m pingeon --poll   → single poll cycle (no GUI, no notifications)
"""

import argparse
import sys
from datetime import date

from . import config, logger
from .calendar_poller import fetch_available_dates, all_days_in_range


def _poll_once() -> None:
    cfg = config.load()
    errors = config.validate(cfg)
    if errors:
        for e in errors:
            print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info("Manual poll started.")
    start = date.fromisoformat(cfg["monitor_start_date"])
    end = date.fromisoformat(cfg["monitor_end_date"])
    available = sorted(fetch_available_dates(cfg["calendar_id"], start, end))
    total = len(all_days_in_range(start, end))
    print(
        f"Range days: {total} | Available: {len(available)} | "
        f"Sample: {[d.isoformat() for d in available[:5]]}"
    )
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
