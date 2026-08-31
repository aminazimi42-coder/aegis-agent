import time
import unittest

from core.tenant_memory import TenantMemoryVault


class TenantMemoryVaultTests(unittest.TestCase):
    def test_store_and_read_for_same_tenant(self):
        vault = TenantMemoryVault(default_ttl_seconds=60)
        vault.store(
            tenant_id="tenant-a",
            key="launch-plan",
            value={"status": "ready"},
            namespace="planning",
        )

        self.assertEqual(
            vault.read("tenant-a", "launch-plan", namespace="planning"),
            {"status": "ready"},
        )

    def test_rejects_cross_tenant_memory_access(self):
        vault = TenantMemoryVault(default_ttl_seconds=60)
        vault.store(
            tenant_id="tenant-a",
            key="secret-note",
            value="top-secret",
            namespace="security",
        )

        with self.assertRaises(PermissionError):
            vault.read("tenant-b", "secret-note", namespace="security")

    def test_expired_memory_entries_are_rejected(self):
        vault = TenantMemoryVault(default_ttl_seconds=0)
        vault.store(
            tenant_id="tenant-a",
            key="timed-cache",
            value="expired",
            namespace="runtime",
        )

        time.sleep(0.05)
        with self.assertRaises(KeyError):
            vault.read("tenant-a", "timed-cache", namespace="runtime")

    def test_namespace_isolation_is_enforced(self):
        vault = TenantMemoryVault(default_ttl_seconds=60)
        vault.store(
            tenant_id="tenant-a",
            key="shared-key",
            value="planning-value",
            namespace="planning",
        )

        self.assertRaises(
            KeyError,
            lambda: vault.read("tenant-a", "shared-key", namespace="execution"),
        )


if __name__ == "__main__":
    unittest.main()
