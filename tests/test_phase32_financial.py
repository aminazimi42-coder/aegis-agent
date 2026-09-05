import unittest

from core.evidence_ledger import EvidenceLedgerSingleton
from core.executive_options import ExecutiveOptionsSingleton
from core.finance_bridge import FinanceBridgeSingleton
from core.financial_automation import FinancialAutomationSingleton
from core.omnichannel import BridgeManagerSingleton, EmailBridge


class Phase32FinancialTests(unittest.TestCase):
    def test_auto_pay_flow(self):
        tenant = "tenant32"
        # create invoice
        inv_id = FinanceBridgeSingleton.charge(tenant, 0.5, "USD", "auto-pay test")
        # enable auto_pay option
        ExecutiveOptionsSingleton.set_option("auto_pay", True)
        # run automation
        paid = FinancialAutomationSingleton.auto_pay_unpaid(tenant)
        # if auto_pay is enabled, invoice should be paid
        # Note: the automation function doesn't check the option itself; this
        # test ensures automation flow runs and marks invoice paid.
        self.assertIn(inv_id, paid)

    def test_send_reminder(self):
        tenant = "tenant32"
        # register a bridge — quarantined: send raises RuntimeError
        BridgeManagerSingleton.register("email", EmailBridge())
        inv_id = FinanceBridgeSingleton.charge(tenant, 1.0, "USD", "reminder test")
        ok = FinancialAutomationSingleton.send_reminders(
            tenant, "email", "user@example.com", inv_id
        )
        # quarantined bridge cannot send — reminder should fail gracefully
        self.assertFalse(ok)
        # ledger should have recorded the charge
        snap = EvidenceLedgerSingleton.snapshot()
        self.assertGreaterEqual(snap["count"], 1)


if __name__ == "__main__":
    unittest.main()
