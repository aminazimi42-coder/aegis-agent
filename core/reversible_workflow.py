from __future__ import annotations

from threading import Lock
from typing import Callable, List


class ReversibleWorkflowManager:
    """Manage a stack of compensating rollback operations for side-effecting actions.

    Usage pattern:
      mgr = ReversibleWorkflowManager()
      mgr.begin()
      mgr.execute(lambda: do_side_effect(), lambda: undo_side_effect())
      if failure: mgr.rollback() else: mgr.commit()
    """

    def __init__(self) -> None:
        self._stack: List[Callable[[], None]] = []
        self._lock = Lock()
        self._active = False

    def begin(self) -> None:
        with self._lock:
            self._stack = []
            self._active = True

    def execute(self, action: Callable[[], object], rollback: Callable[[], None]) -> object:
        """Execute `action` and register `rollback` to be called if a rollback occurs.

        If `action` raises, the rollback will not be executed here — caller should
        call `rollback()` or let the manager handle it.
        """
        if not self._active:
            raise RuntimeError("No active reversible workflow. Call begin() first.")
        result = action()
        with self._lock:
            # insert rollback at top of stack
            self._stack.append(rollback)
        return result

    def commit(self) -> None:
        with self._lock:
            self._stack = []
            self._active = False

    def rollback(self) -> None:
        with self._lock:
            # execute rollbacks in reverse order
            while self._stack:
                try:
                    fn = self._stack.pop()
                    fn()
                except Exception:
                    # swallow to attempt all rollbacks
                    continue
            self._active = False


ReversibleManager = ReversibleWorkflowManager
