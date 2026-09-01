from __future__ import annotations

import time
from typing import Callable

from .evidence_ledger import EvidenceLedgerSingleton
from .scorecard import ScorecardSingleton


class SelfHealingPipeline:
    """Simple self-healing orchestration for retrying and automated rollback.

    Each pipeline step is a callable that either returns True (success) or
    raises an exception. The pipeline will attempt a configurable number of
    retries and record evidence and scorecard entries on failures.
    """

    def __init__(self, retries: int = 2, backoff_seconds: int = 1) -> None:
        self.retries = max(0, int(retries))
        self.backoff_seconds = max(0, int(backoff_seconds))

    def run(self, tenant_id: str, steps: list[Callable[[], bool]]) -> bool:
        for idx, step in enumerate(steps):
            attempt = 0
            while True:
                try:
                    ok = step()
                    if ok:
                        EvidenceLedgerSingleton.append_entry(
                            tenant_id=tenant_id,
                            actor="self_healing",
                            action="step_success",
                            payload={"step": idx},
                        )
                        break
                    else:
                        raise RuntimeError("step returned failure")
                except Exception as exc:
                    attempt += 1
                    EvidenceLedgerSingleton.append_entry(
                        tenant_id=tenant_id,
                        actor="self_healing",
                        action="step_failure",
                        payload={"step": idx, "attempt": attempt, "error": str(exc)},
                    )
                    ScorecardSingleton.record_rollback(tenant_id)
                    if attempt > self.retries:
                        return False
                    time.sleep(self.backoff_seconds)
        return True


DefaultSelfHealing = SelfHealingPipeline()
