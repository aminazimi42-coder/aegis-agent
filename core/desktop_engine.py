from __future__ import annotations

from core.ai_core import AICore

QUARANTINED = True


class DesktopEngine:
    """Lightweight desktop companion core engine.

    Intended for local development and offline execution scenarios where a
    developer or power user runs agent tasks on their workstation.
    """

    def __init__(self) -> None:
        self._core = AICore()

    def run_task(self, task: str) -> dict:
        """Run a single task through the local AI core and return the payload.

        This uses the same `AICore` dispatch path as the server so logic is
        consistent between desktop and server runtimes.
        """
        return self._core.dispatch(task)


DesktopEngineSingleton = DesktopEngine()
