import os
import platform

APP_NAME = "Pingeon"
APP_VERSION = "1.0.0"


def _get_data_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")


DATA_DIR = _get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_FILE = os.path.join(DATA_DIR, "monitor.log")
DB_FILE = os.path.join(DATA_DIR, "state.db")

LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
GUI_LOG_BUFFER_SIZE = 50

DEFAULT_INTERVAL_MINUTES = 2
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 60

FETCH_TIMEOUT_SECONDS = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 30

ICS_URL_TEMPLATE = "https://calendar.google.com/calendar/ical/{calendar_id}/public/basic.ics"

# Cloudflare Worker — serves setup.ps1 and relays alert emails
NOTIFY_ENDPOINT = "https://pingeon.talonbaker.workers.dev"

# Populated by deploy.ps1 — authorizes this app to use the /notify endpoint
NOTIFY_TOKEN = ""
