from __future__ import annotations

import uuid
from decimal import Decimal
from threading import Lock
from typing import Dict

from core.evidence_ledger import EvidenceLedgerSingleton
from core.usage_meter import UsageMeterSingleton


class Invoice:
    def __init__(
        self,
        invoice_id: str,
        tenant_id: str,
        amount: Decimal,
        currency: str,
        description: str,
    ):
        self.invoice_id = invoice_id
        self.tenant_id = tenant_id
        self.amount = amount
        self.currency = currency
        self.description = description
        self.paid = False


class FinanceBridge:
    """Simple local finance/task execution bridge.

    - `charge` records an invoice and appends to the ledger.
    - `pay` marks invoice paid and records ledger event.
    This is a stub to be replaced by integration with a payment gateway.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._invoices: Dict[str, Invoice] = {}

    def charge(
        self,
        tenant_id: str,
        amount: float,
        currency: str = "USD",
        description: str = "charge",
    ) -> str:
        invoice_id = str(uuid.uuid4())
        inv = Invoice(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            amount=Decimal(str(amount)),
            currency=currency,
            description=description,
        )
        with self._lock:
            self._invoices[invoice_id] = inv
            # record as usage (convert dollars to cents as tokens)
            cents = int(inv.amount * 100)
            UsageMeterSingleton.record_usage(tenant_id, tokens=cents, model="finance/charge")
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="finance_bridge",
                action="charge",
                payload={
                    "invoice_id": invoice_id,
                    "amount": str(inv.amount),
                    "currency": currency,
                    "description": description,
                },
            )
        return invoice_id

    def pay(self, invoice_id: str) -> bool:
        with self._lock:
            inv = self._invoices.get(invoice_id)
            if not inv:
                return False
            inv.paid = True
            EvidenceLedgerSingleton.append_entry(
                tenant_id=inv.tenant_id,
                actor="finance_bridge",
                action="pay",
                payload={"invoice_id": invoice_id},
            )
            return True

    def get_invoice(self, invoice_id: str):
        return self._invoices.get(invoice_id)


FinanceBridgeSingleton = FinanceBridge()
