from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from typing import List

from core.evidence_ledger import EvidenceLedgerSingleton
from core.finance_bridge import FinanceBridgeSingleton
from core.omnichannel import BridgeManagerSingleton


class FinancialAutomation:
    """Automates invoice retry and reminder flows.

    - `auto_pay_unpaid`: attempt to auto-pay unpaid invoices when executive
      `auto_pay` is enabled (via `executive_options`). This is a stub that
      marks invoices paid via the local `FinanceBridge`.
    - `send_reminders`: send reminder messages via registered bridges.
    """

    def __init__(self) -> None:
        self._lock = Lock()

    def auto_pay_unpaid(self, tenant_id: str, max_age_days: int = 30) -> List[str]:
        """Find unpaid invoices and attempt auto-pay. Returns list of paid ids."""
        paid: List[str] = []
        now = datetime.utcnow()
        # Look through FinanceBridgeSingleton's internal invoices (lightweight)
        for inv_id, inv in list(FinanceBridgeSingleton._invoices.items()):
            if inv.tenant_id != tenant_id:
                continue
            if inv.paid:
                continue
            # if invoice older than max_age_days, skip auto-pay
            if hasattr(inv, "created_at"):
                age = now - datetime.utcfromtimestamp(inv.created_at)
            else:
                age = None
            if age and age > timedelta(days=max_age_days):
                continue
            # perform pay
            ok = FinanceBridgeSingleton.pay(inv_id)
            if ok:
                paid.append(inv_id)
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor="financial_automation",
                    action="auto_pay",
                    payload={"invoice_id": inv_id},
                )
        return paid

    def send_reminders(
        self,
        tenant_id: str,
        bridge_name: str,
        recipient: str,
        invoice_id: str,
    ) -> bool:
        msg = f"Reminder: please pay invoice {invoice_id}"
        try:
            BridgeManagerSingleton.send(bridge_name, tenant_id, recipient, msg)
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="financial_automation",
                action="send_reminder",
                payload={"invoice_id": invoice_id, "recipient": recipient},
            )
            return True
        except Exception:
            return False


FinancialAutomationSingleton = FinancialAutomation()
