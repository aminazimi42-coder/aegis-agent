import unittest

from core.human_authority import ApprovalLevel, HumanAuthority


class HumanAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.auth = HumanAuthority()

    def test_low_risk_auto(self):
        profile = self.auth.evaluate_risk("Summarize my notes")
        self.assertEqual(profile.level, ApprovalLevel.AUTO)

    def test_keyword_increases_risk(self):
        profile = self.auth.evaluate_risk("Delete user account and remove data")
        self.assertIn(profile.level, (ApprovalLevel.SINGLE_APPROVAL, ApprovalLevel.DUAL_APPROVAL))

    def test_deny_raises(self):
        # craft a long, sensitive action to push score above 0.95
        long_action = "transfer all funds to external holder" * 20
        with self.assertRaises(PermissionError):
            self.auth.check_authorization(long_action, {"tenant_sensitive": True})


if __name__ == "__main__":
    unittest.main()
