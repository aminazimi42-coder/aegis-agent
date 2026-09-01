from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional

from core.evidence_ledger import EvidenceLedgerSingleton


@dataclass
class Commitment:
    commitment_id: str
    tenant_id: str
    task_id: str
    assignee: str
    created_at: float = field(default_factory=time.time)
    due_at: Optional[float] = None
    status: str = "open"


class CommitmentEngine:
    """Records commitments (promises) by actors to execute tasks. Supports
    create, fulfill, cancel, and audit trail via EvidenceLedger.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._commitments: Dict[str, Commitment] = {}

    def create_commitment(
        self,
        tenant_id: str,
        task_id: str,
        assignee: str,
        due_at: Optional[float] = None,
    ) -> Commitment:
        cid = str(uuid.uuid4())
        c = Commitment(
            commitment_id=cid,
            tenant_id=tenant_id,
            task_id=task_id,
            assignee=assignee,
            due_at=due_at,
        )
        with self._lock:
            self._commitments[cid] = c
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="commitment_engine",
                action="create_commitment",
                payload={
                    "commitment_id": cid,
                    "task_id": task_id,
                    "assignee": assignee,
                    "due_at": due_at,
                },
            )
        return c

    def fulfill_commitment(self, commitment_id: str) -> bool:
        with self._lock:
            c = self._commitments.get(commitment_id)
            if not c or c.status != "open":
                return False
            c.status = "fulfilled"
            EvidenceLedgerSingleton.append_entry(
                tenant_id=c.tenant_id,
                actor="commitment_engine",
                action="fulfill_commitment",
                payload={"commitment_id": commitment_id},
            )
            return True

    def cancel_commitment(self, commitment_id: str) -> bool:
        with self._lock:
            c = self._commitments.get(commitment_id)
            if not c or c.status != "open":
                return False
            c.status = "cancelled"
            EvidenceLedgerSingleton.append_entry(
                tenant_id=c.tenant_id,
                actor="commitment_engine",
                action="cancel_commitment",
                payload={"commitment_id": commitment_id},
            )
            return True

    def get(self, commitment_id: str) -> Optional[Commitment]:
        return self._commitments.get(commitment_id)


CommitmentEngineSingleton = CommitmentEngine()
