"""
In-process run state for the polling loop.

Polling runs inside the GUI thread; no scheduled-task or service
registration is needed -- the GUI is the lifecycle owner.
"""

_running: bool = False


def set_running(state: bool) -> None:
    global _running
    _running = state


def is_running() -> bool:
    return _running
