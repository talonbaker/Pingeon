import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler
from datetime import datetime

from .constants import (
    DATA_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, GUI_LOG_BUFFER_SIZE
)

# In-memory ring buffer for the GUI log viewer
_gui_buffer: deque = deque(maxlen=GUI_LOG_BUFFER_SIZE)

_initialized = False


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _init() -> None:
    global _initialized
    if _initialized:
        return
    _ensure_data_dir()

    root = logging.getLogger("pingeon")
    root.setLevel(logging.DEBUG)

    # Rotating file handler
    fh = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(fh)

    _initialized = True


def _record(level: str, message: str) -> None:
    _init()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {level}: {message}"
    _gui_buffer.append(entry)
    logger = logging.getLogger("pingeon")
    getattr(logger, level.lower(), logger.info)(message)


def info(message: str) -> None:
    _record("INFO", message)


def warning(message: str) -> None:
    _record("WARNING", message)


def error(message: str) -> None:
    _record("ERROR", message)


def debug(message: str) -> None:
    _record("DEBUG", message)


def get_recent_logs(count: int = GUI_LOG_BUFFER_SIZE) -> list[str]:
    """Return the most recent log entries for the GUI viewer."""
    entries = list(_gui_buffer)
    return entries[-count:]


def get_log_file_path() -> str:
    return LOG_FILE
