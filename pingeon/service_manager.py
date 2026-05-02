"""
Windows scheduled task registration (optional background mode).

The primary polling loop runs in-process inside the GUI thread so that
no credentials or state need to be persisted for the task scheduler to use.
"""

import platform
import subprocess
import sys

from .constants import TASK_NAME, DATA_DIR
from . import logger


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _run_schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True)


def install_task() -> None:
    if not _is_windows():
        logger.warning("Scheduled tasks are only supported on Windows.")
        return
    result = _run_schtasks(
        "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{sys.executable}" -m pingeon --poll',
        "/SC", "ONCE", "/ST", "00:00", "/SD", "01/01/2099",
        "/RL", "LIMITED", "/F",
    )
    if result.returncode == 0:
        logger.info("Scheduled task registered.")
    else:
        logger.error(f"Task registration failed: {result.stderr.strip()}")


def uninstall_task() -> None:
    if not _is_windows():
        return
    result = _run_schtasks("/Delete", "/TN", TASK_NAME, "/F")
    if result.returncode == 0:
        logger.info("Scheduled task removed.")
    else:
        logger.warning(f"Task removal: {result.stderr.strip()}")


def is_task_registered() -> bool:
    if not _is_windows():
        return False
    return _run_schtasks("/Query", "/TN", TASK_NAME).returncode == 0


# In-process run state (driven by the GUI)
_running: bool = False


def set_running(state: bool) -> None:
    global _running
    _running = state


def is_running() -> bool:
    return _running
