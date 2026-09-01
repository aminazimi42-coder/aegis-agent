from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class LedgerEntry:
    index: int
    timestamp: float
    tenant_id: str
    actor: str
    action: str
    payload: Dict[str, Any]
    prev_hash: Optional[str]
    hash: str


class EvidenceLedger:
    """A simple hash-chained ledger for recording tamper-evident evidence.

    Each entry chains to the previous via SHA-256 over the canonical JSON
    serialization of (prev_hash, timestamp, tenant_id, actor, action, payload).
    """

    def __init__(self) -> None:
        self._entries: List[LedgerEntry] = []

    def _compute_hash(
        self,
        prev_hash: Optional[str],
        timestamp: float,
        tenant_id: str,
        actor: str,
        action: str,
        payload: Dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            {
                "prev_hash": prev_hash,
                "timestamp": timestamp,
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return _sha256_hex(canonical)

    def append_entry(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        payload: Dict[str, Any],
    ) -> LedgerEntry:
        timestamp = time.time()
        prev_hash = self._entries[-1].hash if self._entries else None
        idx = len(self._entries)
        entry_hash = self._compute_hash(
            prev_hash, timestamp, tenant_id, actor, action, payload
        )
        entry = LedgerEntry(
            index=idx,
            timestamp=timestamp,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            payload=payload,
            prev_hash=prev_hash,
            hash=entry_hash,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> List[Dict[str, Any]]:
        return [e.__dict__.copy() for e in self._entries]

    def snapshot(self) -> Dict[str, Any]:
        return {"count": len(self._entries), "entries": self.entries()}

    def verify_chain(self) -> bool:
        prev_hash = None
        for e in self._entries:
            recomputed = self._compute_hash(
                e.prev_hash, e.timestamp, e.tenant_id, e.actor, e.action, e.payload
            )
            if recomputed != e.hash:
                return False
            if e.prev_hash != prev_hash:
                return False
            prev_hash = e.hash
        return True

    def find_tamper_indices(self) -> List[int]:
        bad: List[int] = []
        prev_hash = None
        for e in self._entries:
            recomputed = self._compute_hash(
                e.prev_hash, e.timestamp, e.tenant_id, e.actor, e.action, e.payload
            )
            if recomputed != e.hash or e.prev_hash != prev_hash:
                bad.append(e.index)
            prev_hash = e.hash
        return bad

    def remove_last(self, n: int = 1) -> int:
        """Remove the last `n` entries from the ledger and return how many removed.

        Useful for compensating rollbacks in tests or orchestrated rollback flows.
        """
        if n <= 0:
            return 0
        removed = 0
        for _ in range(min(n, len(self._entries))):
            self._entries.pop()
            removed += 1
        return removed


EvidenceLedgerSingleton = EvidenceLedger()
