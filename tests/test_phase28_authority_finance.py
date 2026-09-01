import unittest

from core.authority_matrix import AuthorityMatrixSingleton
from core.data_governance import ConsentStoreSingleton, PolicyEngineSingleton
from core.finance_bridge import FinanceBridgeSingleton
from core.secure_governance import AuthorizationError, authorize_action


class Phase28Tests(unittest.TestCase):
    def setUp(self) -> None:
        # define admin role
        AuthorityMatrixSingleton.define_role("admin", ["execute_task", "manage_billing"])

    def test_authorized_action(self):
        tenant = "tenant28"
        actor = "alice"
        # grant consent and assign role
        PolicyEngineSingleton.add_allow("data:task")
        ConsentStoreSingleton.grant(tenant, actor, ["data:task"])
        AuthorityMatrixSingleton.assign_role(tenant, actor, "admin")
        # should authorize
        res = authorize_action(tenant, actor, "execute_task", ["data:task"])
        self.assertTrue(res.get("allowed"))

    def test_finance_charge_and_pay(self):
        tenant = "tenant28"
        inv = FinanceBridgeSingleton.charge(tenant, 1.23, "USD", "task-exec")
        self.assertIsNotNone(inv)
        ok = FinanceBridgeSingleton.pay(inv)
        self.assertTrue(ok)

    def test_unauthorized_fails(self):
        tenant = "tenant28"
        actor = "bob"
        PolicyEngineSingleton.add_allow("data:task")
        ConsentStoreSingleton.grant(tenant, actor, ["data:task"])
        # bob has no role -> should raise AuthorizationError
        with self.assertRaises(AuthorizationError):
            authorize_action(tenant, actor, "execute_task", ["data:task"])


if __name__ == "__main__":
    unittest.main()
