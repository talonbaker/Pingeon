import logging
import os
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler

from .constants import DATA_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, GUI_LOG_BUFFER_SIZE

_gui_buffer: deque = deque(maxlen=GUI_LOG_BUFFER_SIZE)
_initialized = False


def _init() -> None:
    global _initialized
    if _initialized:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    root = logging.getLogger("pingeon")
    root.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT, encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(fh)
    _initialized = True


def _record(level: str, message: str) -> None:
    _init()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _gui_buffer.append(f"[{ts}] {level}: {message}")
    getattr(logging.getLogger("pingeon"), level.lower(), logging.getLogger("pingeon").info)(message)


def info(message: str) -> None:    _record("INFO", message)
def warning(message: str) -> None: _record("WARNING", message)
def error(message: str) -> None:   _record("ERROR", message)
def debug(message: str) -> None:   _record("DEBUG", message)


def get_recent_logs(count: int = GUI_LOG_BUFFER_SIZE) -> list[str]:
    return list(_gui_buffer)[-count:]


def get_log_file_path() -> str:
    return LOG_FILE
