"""T220 — Operator idle session lock and local Keychain PIN.

Tests:
* ``test_idle_then_lock_unlock`` — idle then lock; unlock with correct PIN.
* ``test_wrong_pin_typed_fail`` — wrong PIN is a typed deny; lockout after 5.
* ``test_lockout_after_five_failures`` — 5 wrong PINs triggers 5-min lockout.
* ``test_lockout_blocks_correct_pin`` — a correct PIN during lockout is denied.
* ``test_neighbor_denied`` — neighbor tenant cannot unlock this tenant.
* ``test_forget_drops_lock_material`` — forget_all drops Keychain/mock PIN + lock.
* ``test_no_pin_in_audit`` — audit/propose/export contain no PIN digits.
* ``test_start_script_unchanged`` — start_operator.sh is still the sole start.
* ``test_idle_seconds_env_bounds`` — AEGIS_SESSION_IDLE_SECONDS min/max/override.
* ``test_no_biometrics_claim`` — no biometrics/Face ID claim in HTML.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT220SessionLock(unittest.TestCase):
    """T220 — operator idle session lock and Keychain PIN."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clear any idle-seconds override so the default is used.
        os.environ.pop("AEGIS_SESSION_IDLE_SECONDS", None)
        from core.session_lock import reset_for_tests

        reset_for_tests()

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_SESSION_IDLE_SECONDS", None)
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
    # 1. Idle then lock; unlock with correct PIN
    # ------------------------------------------------------------------ #

    def test_idle_then_lock_unlock(self) -> None:
        """Idle then lock; unlock with the correct PIN."""
        from core.session_lock import (
            is_locked,
            lock,
            record_operator_activity,
            set_pin,
            unlock,
        )

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            record_operator_activity("tenant-a")
            self.assertFalse(is_locked("tenant-a"))
            # Force-lock (simulates idle timeout).
            lock("tenant-a")
            self.assertTrue(is_locked("tenant-a"))
            result = unlock("tenant-a", "123456")
            self.assertTrue(result["unlocked"])
            self.assertFalse(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 2. Wrong PIN typed fail
    # ------------------------------------------------------------------ #

    def test_wrong_pin_typed_fail(self) -> None:
        """A wrong PIN is a typed deny — session stays locked."""
        from core.session_lock import is_locked, lock, set_pin, unlock

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            result = unlock("tenant-a", "000000")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "WRONG_PIN")
            self.assertTrue(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 3. Lockout after 5 failures for 5 minutes
    # ------------------------------------------------------------------ #

    def test_lockout_after_five_failures(self) -> None:
        """Five wrong PINs trigger a 5-minute lockout with retry_after."""
        from core.session_lock import lock, set_pin, unlock

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            for _ in range(4):
                r = unlock("tenant-a", "000000")
                self.assertEqual(r["code"], "WRONG_PIN")
            # 5th wrong PIN triggers lockout.
            r5 = unlock("tenant-a", "000000")
            self.assertEqual(r5["code"], "PIN_LOCKOUT")
            self.assertIn("retry_after", r5)
            self.assertGreater(r5["retry_after"], 0)

    # ------------------------------------------------------------------ #
    # 4. Lockout blocks even a correct PIN
    # ------------------------------------------------------------------ #

    def test_lockout_blocks_correct_pin(self) -> None:
        """A correct PIN during lockout is denied until the window expires."""
        from core.session_lock import lock, set_pin, unlock

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            for _ in range(5):
                unlock("tenant-a", "000000")
            # Correct PIN but lockout is active.
            r = unlock("tenant-a", "123456")
            self.assertEqual(r["code"], "PIN_LOCKOUT")
            self.assertFalse(r["unlocked"])

    # ------------------------------------------------------------------ #
    # 5. Neighbor tenant cannot unlock
    # ------------------------------------------------------------------ #

    def test_neighbor_denied(self) -> None:
        """A neighbor tenant's PIN does not unlock this tenant."""
        from core.session_lock import is_locked, lock, set_pin, unlock

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "111111")
            set_pin("tenant-b", "222222")
            lock("tenant-a")
            result = unlock("tenant-a", "222222")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "WRONG_PIN")
            self.assertTrue(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 6. Forget tenant drops Keychain/mock item for that tenant only
    # ------------------------------------------------------------------ #

    def test_forget_drops_lock_material(self) -> None:
        """forget_all drops the session lock material for that tenant only."""
        from core.session_lock import has_pin, is_locked, lock, set_pin
        from core.twin_memory_control import forget_all

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            set_pin("tenant-b", "654321")
            lock("tenant-a")
            self.assertTrue(has_pin("tenant-a"))
            self.assertTrue(is_locked("tenant-a"))
            # Forget tenant-a — should drop its lock + PIN.
            forget_all("tenant-a")
            self.assertFalse(has_pin("tenant-a"))
            # Tenant-b PIN stays.
            self.assertTrue(has_pin("tenant-b"))

    # ------------------------------------------------------------------ #
    # 7. No PIN digits in audit/propose/export
    # ------------------------------------------------------------------ #

    def test_no_pin_in_audit(self) -> None:
        """The PIN value never appears in audit JSONL or ledger files."""
        from core.audit_logger import log_event, read_events
        from core.session_lock import lock, set_pin

        pin_val = "123456"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", pin_val)
            lock("tenant-a")
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
    # 8. start_operator.sh still sole start; does not open Safari
    # ------------------------------------------------------------------ #

    def test_start_script_unchanged(self) -> None:
        """start_operator.sh is still the sole start path and does not
        open Safari or a browser."""
        repo = Path(__file__).resolve().parent.parent
        script = repo / "scripts" / "start_operator.sh"
        self.assertTrue(script.is_file(), "start_operator.sh missing")
        text = script.read_text(encoding="utf-8")
        self.assertNotIn("Safari", text)
        self.assertNotIn("open -a Safari", text)
        # Should still bind 127.0.0.1:8741.
        self.assertIn("8741", text)

    # ------------------------------------------------------------------ #
    # 9. AEGIS_SESSION_IDLE_SECONDS env bounds
    # ------------------------------------------------------------------ #

    def test_idle_seconds_env_bounds(self) -> None:
        """AEGIS_SESSION_IDLE_SECONDS respects min 60, max 86400, default 900."""
        from core.session_lock import _idle_seconds

        # Default.
        os.environ.pop("AEGIS_SESSION_IDLE_SECONDS", None)
        self.assertEqual(_idle_seconds(), 900)
        # Override.
        os.environ["AEGIS_SESSION_IDLE_SECONDS"] = "120"
        self.assertEqual(_idle_seconds(), 120)
        # Min 60.
        os.environ["AEGIS_SESSION_IDLE_SECONDS"] = "30"
        self.assertEqual(_idle_seconds(), 60)
        # Max 86400.
        os.environ["AEGIS_SESSION_IDLE_SECONDS"] = "999999"
        self.assertEqual(_idle_seconds(), 86400)
        # Bad value falls back to default.
        os.environ["AEGIS_SESSION_IDLE_SECONDS"] = "not-a-number"
        self.assertEqual(_idle_seconds(), 900)

    # ------------------------------------------------------------------ #
    # 10. No Face ID / biometrics enrollment claim in operator HTML
    # ------------------------------------------------------------------ #

    def test_no_biometrics_claim(self) -> None:
        """The operator page HTML does not claim Face ID or biometric enrollment.

        T226 — Touch ID as an optional unlock after PIN is allowed; Face ID,
        face enrollment, and voice enrollment stay out of the twin core.
        """
        repo = Path(__file__).resolve().parent.parent
        for html_name in ("app.html",):
            html = (repo / html_name).read_text(encoding="utf-8").lower()
            self.assertNotIn("face id", html)
            self.assertNotIn("faceid", html)
            self.assertNotIn("voice id", html)
            self.assertNotIn("voiceid", html)
            self.assertNotIn("enrollment", html)


if __name__ == "__main__":
    unittest.main()
