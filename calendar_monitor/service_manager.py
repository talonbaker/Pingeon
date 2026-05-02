"""
Windows scheduled task manager.

Creates a per-user scheduled task that runs the poller on demand.
The task is NOT set to run on a fixed schedule — the GUI's polling loop
runs in-process while the app is open, which avoids storing the SMTP
password anywhere the task scheduler could reach it.

The task entry is kept for future background-service upgrades.
"""

import subprocess
import sys
import os
import platform

from .constants import TASK_NAME, DATA_DIR
from . import logger


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _python_exe() -> str:
    return sys.executable


def _script_args() -> str:
    """Arguments passed to python when the task fires."""
    return f'"{_python_exe()}" -m photographer_monitor --poll'


# ── Windows task operations ──────────────────────────────────────────────────

def _run_schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        text=True,
    )


def install_task() -> None:
    """Register the scheduled task (does NOT enable automatic execution)."""
    if not _is_windows():
        logger.warning("Scheduled task install is only supported on Windows.")
        return

    result = _run_schtasks(
        "/Create",
        "/TN", TASK_NAME,
        "/TR", _script_args(),
        "/SC", "ONCE",
        "/ST", "00:00",
        "/SD", "01/01/2099",   # Far future — task is triggered manually
        "/RL", "LIMITED",
        "/F",                  # Force overwrite if exists
    )
    if result.returncode == 0:
        logger.info("Windows scheduled task registered.")
    else:
        logger.error(f"Task registration failed: {result.stderr.strip()}")


def uninstall_task() -> None:
    if not _is_windows():
        return
    result = _run_schtasks("/Delete", "/TN", TASK_NAME, "/F")
    if result.returncode == 0:
        logger.info("Windows scheduled task removed.")
    else:
        logger.warning(f"Task removal: {result.stderr.strip()}")


def is_task_registered() -> bool:
    if not _is_windows():
        return False
    result = _run_schtasks("/Query", "/TN", TASK_NAME)
    return result.returncode == 0


# ── In-process polling state (used by the GUI) ───────────────────────────────
# The GUI drives the polling loop directly (threading.Timer) so the password
# never needs to be persisted anywhere on disk.

_running: bool = False


def set_running(state: bool) -> None:
    global _running
    _running = state


def is_running() -> bool:
    return _running
