import os
import tempfile
import time
import unittest

from core.tenant_memory import TenantMemoryVault


class TenantMemoryVaultTests(unittest.TestCase):
    def test_store_read_delete_and_ttl(self):
        tm = TenantMemoryVault(default_ttl_seconds=1, master_key="testkey")
        tm.store(tenant_id="t1", key="k1", value={"x": 1}, namespace="ns")
        self.assertEqual(tm.read("t1", "k1", namespace="ns"), {"x": 1})
        time.sleep(1.1)
        with self.assertRaises(KeyError):
            tm.read("t1", "k1", namespace="ns")

    def test_forget_namespace_and_matching(self):
        tm = TenantMemoryVault(default_ttl_seconds=60, master_key="testkey")
        tm.store(tenant_id="alpha", key="keep", value="v1", namespace="ns")
        tm.store(tenant_id="alpha", key="del_me", value="secret", namespace="ns")

        def predicate(k, v):
            return k.startswith("del_") or (isinstance(v, str) and "secret" in v)

        removed = tm.forget_matching("alpha", predicate)
        self.assertGreaterEqual(removed, 1)

        # forget whole namespace
        tm.store(tenant_id="alpha", key="a", value=1, namespace="other")
        removed_ns = tm.forget_namespace("alpha", namespace="other")
        self.assertEqual(removed_ns, 1)

    def test_rag_storage_path_and_metadata(self):
        cwd = os.getcwd()
        tmpdir = tempfile.TemporaryDirectory()
        os.chdir(tmpdir.name)
        try:
            tm = TenantMemoryVault(default_ttl_seconds=60, master_key="rotate-me")
            path = tm.rag_storage_path("tenant42", namespace="embeddings")
            self.assertTrue(os.path.isdir(path))
            meta = tm.get_encryption_metadata()
            self.assertIn("algorithm", meta)
            self.assertIn("master_key_fingerprint", meta)
            old_fp = meta["master_key_fingerprint"]
            tm.rotate_master_key("new-key")
            new_fp = tm.get_encryption_metadata()["master_key_fingerprint"]
            self.assertNotEqual(old_fp, new_fp)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
