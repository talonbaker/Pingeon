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

LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
GUI_LOG_BUFFER_SIZE = 50

DEFAULT_INTERVAL_MINUTES = 2
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 60

FETCH_TIMEOUT_SECONDS = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 30

# Google Appointment Scheduling -- public, unauthenticated booking-page API.
# The API key below is the same one the booking page itself uses; it is
# embedded in the page HTML and rate-limited per origin, not per user.
APPT_API_URL = (
    "https://calendar-pa.clients6.google.com"
    "/$rpc/google.internal.calendar.v1.AppointmentBookingService/ListAvailableSlots"
)
APPT_API_KEY = "AIzaSyA7GKm43l8WNxlLTjsldq9z9n80CL6KW4U"
# Server rejects windows much wider than ~30 days with INVALID_ARGUMENT.
APPT_WINDOW_DAYS = 30

TASK_NAME = "Pingeon"

# Cloudflare Worker — serves setup.ps1 and relays alert emails
NOTIFY_ENDPOINT = "https://pingeon.talonbaker.workers.dev"

# Populated by deploy.ps1 — authorizes this app to use the /notify endpoint
NOTIFY_TOKEN = ""
