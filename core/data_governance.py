from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, List

from core.evidence_ledger import EvidenceLedgerSingleton


@dataclass
class ConsentRecord:
    tenant_id: str
    subject_id: str
    scope: List[str]
    granted: bool


class ConsentStore:
    """In-memory consent store for local governance/testing."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._store: Dict[str, ConsentRecord] = {}

    def grant(self, tenant_id: str, subject_id: str, scope: List[str]) -> None:
        key = f"{tenant_id}:{subject_id}"
        rec = ConsentRecord(tenant_id=tenant_id, subject_id=subject_id, scope=scope, granted=True)
        with self._lock:
            self._store[key] = rec
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor=subject_id,
                action="consent_granted",
                payload={"scope": scope},
            )

    def revoke(self, tenant_id: str, subject_id: str) -> None:
        key = f"{tenant_id}:{subject_id}"
        with self._lock:
            if key in self._store:
                del self._store[key]
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor=subject_id,
                    action="consent_revoked",
                    payload={},
                )

    def check(self, tenant_id: str, subject_id: str, required_scope: List[str]) -> bool:
        key = f"{tenant_id}:{subject_id}"
        with self._lock:
            rec = self._store.get(key)
            if not rec or not rec.granted:
                return False
            return all(s in rec.scope for s in required_scope)


ConsentStoreSingleton = ConsentStore()


class PolicyEngine:
    """Simple allow/deny policies for local governance.

    Policies are strings representing allowed prefixes for data types or
    operations. This is intentionally small for Phase26 local governance.
    """

    def __init__(self) -> None:
        self._allow_list: List[str] = []

    def add_allow(self, pattern: str) -> None:
        self._allow_list.append(pattern)

    def allowed(self, data_label: str) -> bool:
        return any(data_label.startswith(p) for p in self._allow_list)


PolicyEngineSingleton = PolicyEngine()
