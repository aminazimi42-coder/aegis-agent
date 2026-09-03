"""T55 — Reproducible build contract tests.

Verifies that:
- The declared HTTP test client dependency (httpx) is importable.
- The default key store (kms_adapter) round-trips under AEGIS_DATA_DIR.
- Persistence failures are not silently swallowed.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestT55BuildContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="aegis_t55_")
        self._old_data_dir = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmpdir

    def tearDown(self) -> None:
        if self._old_data_dir is not None:
            os.environ["AEGIS_DATA_DIR"] = self._old_data_dir
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)
        # Clean up tmpdir
        kms_dir = Path(self._tmpdir) / ".kms"
        if kms_dir.exists():
            for p in kms_dir.iterdir():
                p.unlink()
            kms_dir.rmdir()
        Path(self._tmpdir).rmdir()

    def test_declared_test_client_dependency_imports(self) -> None:
        """httpx (the Starlette testclient fallback) must import successfully."""
        import httpx  # noqa: F401

    def test_default_key_store_round_trip_under_aegis_data_dir(self) -> None:
        """register_private_key persists via kms_adapter and load_key retrieves it."""
        from core.key_manager import KeyManager
        from core.kms_adapter import load_key

        km = KeyManager()
        name = "t55-roundtrip"
        priv = b"t55-secret"
        km.register_private_key(name, priv)

        stored = load_key(name)
        self.assertIsNotNone(stored)
        self.assertEqual(stored, priv)

    def test_persistence_failure_is_not_swallowed(self) -> None:
        """If the store hook raises, register_private_key must propagate the error."""
        import core.key_manager as key_manager
        from core.key_manager import KeyManager

        km = KeyManager()
        original_store = key_manager.kms_store_key

        def _failing_store(name: str, pem: bytes) -> None:
            raise OSError("simulated persistence failure")

        key_manager.kms_store_key = _failing_store  # type: ignore[assignment]
        try:
            with self.assertRaises((OSError, RuntimeError, Exception)):
                km.register_private_key("t55-fail", b"should-fail")
        finally:
            key_manager.kms_store_key = original_store  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
