import os
import sys
import platform

APP_NAME = "PhotographerMonitor"
APP_VERSION = "1.0.0"

# Platform-aware data directory
def _get_data_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")

DATA_DIR = _get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_FILE = os.path.join(DATA_DIR, "monitor.log")
DB_FILE = os.path.join(DATA_DIR, "state.db")

# Logging
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5
GUI_LOG_BUFFER_SIZE = 50

# Polling
DEFAULT_INTERVAL_MINUTES = 2
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 60

# Network
FETCH_TIMEOUT_SECONDS = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 30

# Gmail SMTP
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ICS URL template — only Google Calendar ICS feeds are fetched
ICS_URL_TEMPLATE = "https://calendar.google.com/calendar/ical/{calendar_id}/public/basic.ics"

# Windows scheduled task name
TASK_NAME = "PhotographerMonitor"
