from __future__ import annotations

from threading import Lock
from typing import Dict

from core.evidence_ledger import EvidenceLedgerSingleton


class ExecutiveOptions:
    """Stores runtime toggles for executive automation features.

    Example toggles: `auto_pay` (boolean), `reminder_bridge` (string).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._opts: Dict[str, object] = {}

    def set_option(self, key: str, value: object) -> None:
        with self._lock:
            self._opts[key] = value
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="executive_options",
                action="set_option",
                payload={"key": key, "value": str(value)},
            )

    def get_option(self, key: str, default: object = None) -> object:
        with self._lock:
            return self._opts.get(key, default)


ExecutiveOptionsSingleton = ExecutiveOptions()
