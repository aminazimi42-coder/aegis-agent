from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional

from core.evidence_ledger import EvidenceLedgerSingleton


def _fingerprint(attrs: Dict[str, str]) -> str:
    # stable deterministic fingerprint of identity attributes
    s = json.dumps(attrs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class Identity:
    subject_id: str
    tenant_id: str
    attrs: Dict[str, str]
    fingerprint: str


class CognitiveIdentityEngine:
    """Simple cognitive identity engine that builds identity profiles and
    computes deterministic fingerprints. It links evidence and supports
    fuzzy merges by fingerprint.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._identities: Dict[str, Identity] = {}

    def enroll(self, tenant_id: str, subject_id: str, attrs: Dict[str, str]) -> Identity:
        fp = _fingerprint(attrs)
        ident = Identity(
            subject_id=subject_id,
            tenant_id=tenant_id,
            attrs=dict(attrs),
            fingerprint=fp,
        )
        with self._lock:
            self._identities[f"{tenant_id}:{subject_id}"] = ident
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="cognitive_identity",
                action="enroll",
                payload={"subject_id": subject_id, "fingerprint": fp},
            )
        return ident

    def resolve_by_fingerprint(self, fingerprint: str) -> List[Identity]:
        with self._lock:
            return [i for i in self._identities.values() if i.fingerprint == fingerprint]

    def link(self, tenant_id: str, subject_id: str, other_subject_id: str) -> bool:
        key = f"{tenant_id}:{subject_id}"
        key2 = f"{tenant_id}:{other_subject_id}"
        with self._lock:
            if key in self._identities and key2 in self._identities:
                # record link in ledger
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor="cognitive_identity",
                    action="link",
                    payload={"a": subject_id, "b": other_subject_id},
                )
                return True
            return False

    def get(self, tenant_id: str, subject_id: str) -> Optional[Identity]:
        return self._identities.get(f"{tenant_id}:{subject_id}")


CognitiveIdentitySingleton = CognitiveIdentityEngine()
