"""T214 — Operator idle lock and local Keychain PIN.

Tests:
* ``test_lock_blocks_propose`` — idle or forced lock blocks propose.
* ``test_lock_blocks_approve`` — idle or forced lock blocks approve.
* ``test_correct_pin_unlocks`` — correct PIN unlocks the session.
* ``test_wrong_pin_typed_fail`` — wrong PIN is a typed deny.
* ``test_neighbor_cannot_unlock`` — a neighbor tenant cannot unlock.
* ``test_pin_not_in_audit`` — the PIN value is absent from ledger/audit.
* ``test_core_has_no_stripe`` — core/ has no stripe token.
* ``test_no_face_voice_in_operator_html`` — no face/voice strings in the
  operator page HTML.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT214SessionLock(unittest.TestCase):
    """T214 — operator idle lock and Keychain PIN."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Reset in-memory state between tests.
        from core.session_lock import reset_for_tests

        reset_for_tests()

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        from core.session_lock import reset_for_tests

        reset_for_tests()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _mock_keychain(self) -> mock.MagicMock:
        """Return a mock keychain store for PIN tests."""
        store = mock.MagicMock()
        values: dict = {}

        def _get(service: str, account: str) -> str | None:
            return values.get((service, account))

        def _set(service: str, account: str, value: str) -> None:
            values[(service, account)] = value

        store.get = mock.Mock(side_effect=_get)
        store.set = mock.Mock(side_effect=_set)
        return store

    # ------------------------------------------------------------------ #
    # 1. Lock blocks propose
    # ------------------------------------------------------------------ #

    def test_lock_blocks_propose(self) -> None:
        """Forced lock blocks the propose route."""
        from app.server import create_app
        from core.session_lock import lock, set_pin
        from fastapi.testclient import TestClient

        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "tenant-a", "text": "test task", "training": True},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("code"), "SESSION_LOCKED")
        self.assertEqual(body.get("count"), 0)

    # ------------------------------------------------------------------ #
    # 2. Lock blocks approve
    # ------------------------------------------------------------------ #

    def test_lock_blocks_approve(self) -> None:
        """Forced lock blocks the approve route."""
        from app.server import create_app
        from core.session_lock import lock, set_pin
        from fastapi.testclient import TestClient

        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/actions/fake-action-id/approve",
            json={
                "tenant_id": "tenant-a",
                "actor_id": "operator",
                "expected_payload_sha256": "abc",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("code"), "SESSION_LOCKED")

    # ------------------------------------------------------------------ #
    # 3. Correct PIN unlocks
    # ------------------------------------------------------------------ #

    def test_correct_pin_unlocks(self) -> None:
        """A correct PIN unlocks the session."""
        from core.session_lock import is_locked, lock, set_pin, unlock

        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            self.assertTrue(is_locked("tenant-a"))
            result = unlock("tenant-a", "123456")
            self.assertTrue(result["unlocked"])
            self.assertFalse(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 4. Wrong PIN typed fail
    # ------------------------------------------------------------------ #

    def test_wrong_pin_typed_fail(self) -> None:
        """A wrong PIN is a typed deny — session stays locked."""
        from core.session_lock import is_locked, lock, set_pin, unlock

        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            result = unlock("tenant-a", "000000")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "WRONG_PIN")
            self.assertTrue(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 5. Neighbor cannot unlock
    # ------------------------------------------------------------------ #

    def test_neighbor_cannot_unlock(self) -> None:
        """A neighbor tenant's PIN does not unlock this tenant."""
        from core.session_lock import is_locked, lock, set_pin, unlock

        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", "111111")
            set_pin("tenant-b", "222222")
            lock("tenant-a")
            # tenant-b's PIN should not unlock tenant-a.
            result = unlock("tenant-a", "222222")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "WRONG_PIN")
            self.assertTrue(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 6. PIN absent from ledger/audit plaintext
    # ------------------------------------------------------------------ #

    def test_pin_not_in_audit(self) -> None:
        """The PIN value never appears in audit JSONL or ledger files."""
        from core.audit_logger import log_event, read_events
        from core.session_lock import lock, set_pin

        pin_val = "123456"
        with mock.patch("core.session_lock.get_store", return_value=self._mock_keychain()):
            set_pin("tenant-a", pin_val)
            lock("tenant-a")
        # Write an audit event.
        log_event("propose", "test-action-id", extra={"tenant_id": "tenant-a"})
        events = read_events()
        for ev in events:
            ev_str = json.dumps(ev)
            self.assertNotIn(pin_val, ev_str)
        # Also scan the audit directory files on disk.
        audit_dir = Path(self._tmp) / "audit"
        if audit_dir.is_dir():
            for f in audit_dir.glob("*.jsonl"):
                text = f.read_text(encoding="utf-8")
                self.assertNotIn(pin_val, text)

    # ------------------------------------------------------------------ #
    # 7. core/ has no stripe token
    # ------------------------------------------------------------------ #

    def test_core_has_no_stripe(self) -> None:
        """core/ source files contain no stripe token."""
        core_dir = Path(__file__).resolve().parent.parent / "core"
        for p in core_dir.glob("*.py"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn(
                "stripe",
                text.lower(),
                f"stripe token found in {p.name}",
            )

    # ------------------------------------------------------------------ #
    # 8. No face/voice strings in operator HTML
    # ------------------------------------------------------------------ #

    def test_no_face_voice_in_operator_html(self) -> None:
        """The operator page HTML contains no face/voice strings."""
        html_path = Path(__file__).resolve().parent.parent / "app.html"
        html = html_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("face id", html)
        self.assertNotIn("faceid", html)
        self.assertNotIn("voice id", html)
        self.assertNotIn("voiceid", html)
        self.assertNotIn("biometric", html)


if __name__ == "__main__":
    unittest.main()
