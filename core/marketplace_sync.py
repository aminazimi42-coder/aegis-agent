from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Dict, List

from core.evidence_ledger import EvidenceLedgerSingleton

MARKET_DIR = Path(".market")
MARKET_DIR.mkdir(exist_ok=True)


class MarketplaceSync:
    """Simple local capsule marketplace sync.

    Stores capsule metadata files locally and records sync events to the ledger.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._index: Dict[str, Dict[str, str]] = {}

    def register_capsule(self, tenant_id: str, capsule_id: str, metadata: Dict[str, str]) -> None:
        with self._lock:
            p = MARKET_DIR / f"{capsule_id}.json"
            p.write_text(str(metadata))
            self._index[capsule_id] = metadata
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="marketplace/sync",
                action="register_capsule",
                payload={"capsule_id": capsule_id, "metadata": metadata},
            )

    def list_capsules(self) -> List[str]:
        with self._lock:
            return list(self._index.keys())


MarketplaceSyncSingleton = MarketplaceSync()
