"""T226 — Optional Touch ID after PIN, mock in CI.

Tests:
* ``test_pin_still_required_when_touch_id_unavailable`` — PIN is still the
  primary unlock when Touch ID is unavailable.
* ``test_mock_ok_unlocks_lock_only`` — mock_ok unlocks the session lock
  but does not execute anything.
* ``test_mock_cancel_stays_locked`` — mock_cancel stays locked with a
  typed message.
* ``test_neighbor_isolated`` — a neighbor tenant's lock is not affected.
* ``test_forget_drops_touch_id_lock`` — forget_all drops that tenant's
  lock material.
* ``test_no_stripe_in_core`` — core/ has no stripe token.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT226TouchId(unittest.TestCase):
    """T226 — optional Touch ID after PIN, mock in CI."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Force the mock adapter (CI/Linux behavior) even on Darwin.
        os.environ["AEGIS_TOUCH_ID_FORCE_MOCK"] = "1"
        os.environ["AEGIS_TOUCH_ID_MOCK_AVAILABLE"] = "1"
        os.environ.pop("AEGIS_TOUCH_ID_MOCK_RESULT", None)
        from core.session_lock import reset_for_tests

        reset_for_tests()

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_TOUCH_ID_FORCE_MOCK", None)
        os.environ.pop("AEGIS_TOUCH_ID_MOCK_AVAILABLE", None)
        os.environ.pop("AEGIS_TOUCH_ID_MOCK_RESULT", None)
        from core.session_lock import reset_for_tests

        reset_for_tests()

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
    # 1. PIN still required when Touch ID unavailable
    # ------------------------------------------------------------------ #

    def test_pin_still_required_when_touch_id_unavailable(self) -> None:
        """PIN is still the primary unlock when Touch ID is unavailable."""
        from core.session_lock import (
            is_locked,
            lock,
            set_pin,
            touch_id_available,
            unlock_with_touch_id,
        )

        os.environ["AEGIS_TOUCH_ID_MOCK_AVAILABLE"] = "0"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            self.assertTrue(is_locked("tenant-a"))
            self.assertFalse(touch_id_available())
            result = unlock_with_touch_id("tenant-a")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "TOUCH_ID_UNAVAILABLE")
            self.assertTrue(is_locked("tenant-a"))
            # PIN still works to unlock.
            from core.session_lock import unlock

            ok = unlock("tenant-a", "123456")
            self.assertTrue(ok["unlocked"])
            self.assertFalse(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 2. mock_ok unlocks the session lock only — does not execute
    # ------------------------------------------------------------------ #

    def test_mock_ok_unlocks_lock_only(self) -> None:
        """mock_ok unlocks the session lock but does not execute anything."""
        from core.session_lock import (
            is_locked,
            lock,
            set_pin,
            touch_id_available,
            unlock_with_touch_id,
        )

        os.environ["AEGIS_TOUCH_ID_MOCK_RESULT"] = "mock_ok"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            self.assertTrue(is_locked("tenant-a"))
            self.assertTrue(touch_id_available())
            result = unlock_with_touch_id("tenant-a")
            self.assertTrue(result["unlocked"])
            self.assertEqual(result["code"], "SESSION_UNLOCKED_TOUCH_ID")
            self.assertFalse(is_locked("tenant-a"))
            # Verify the result has no execute side-effect — it only unlocks.
            self.assertNotIn("executed", result)

    # ------------------------------------------------------------------ #
    # 3. mock_cancel stays locked
    # ------------------------------------------------------------------ #

    def test_mock_cancel_stays_locked(self) -> None:
        """mock_cancel stays locked with a typed message."""
        from core.session_lock import (
            is_locked,
            lock,
            set_pin,
            touch_id_available,
            unlock_with_touch_id,
        )

        os.environ["AEGIS_TOUCH_ID_MOCK_RESULT"] = "mock_cancel"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            self.assertTrue(touch_id_available())
            result = unlock_with_touch_id("tenant-a")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "TOUCH_ID_CANCELLED")
            self.assertTrue(is_locked("tenant-a"))

    # ------------------------------------------------------------------ #
    # 4. Neighbor tenant lock is isolated
    # ------------------------------------------------------------------ #

    def test_neighbor_isolated(self) -> None:
        """A Touch ID unlock on tenant-a does not unlock tenant-b."""
        from core.session_lock import (
            is_locked,
            lock,
            set_pin,
            touch_id_available,
            unlock_with_touch_id,
        )

        os.environ["AEGIS_TOUCH_ID_MOCK_RESULT"] = "mock_ok"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "111111")
            set_pin("tenant-b", "222222")
            lock("tenant-a")
            lock("tenant-b")
            self.assertTrue(is_locked("tenant-a"))
            self.assertTrue(is_locked("tenant-b"))
            self.assertTrue(touch_id_available())
            result = unlock_with_touch_id("tenant-a")
            self.assertTrue(result["unlocked"])
            self.assertFalse(is_locked("tenant-a"))
            # Neighbor stays locked.
            self.assertTrue(is_locked("tenant-b"))

    # ------------------------------------------------------------------ #
    # 5. Forget drops that tenant's lock material
    # ------------------------------------------------------------------ #

    def test_forget_drops_touch_id_lock(self) -> None:
        """forget_all drops the session lock material for that tenant only."""
        from core.session_lock import has_pin, is_locked, lock, set_pin
        from core.twin_memory_control import forget_all

        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            set_pin("tenant-b", "654321")
            lock("tenant-a")
            lock("tenant-b")
            self.assertTrue(is_locked("tenant-a"))
            self.assertTrue(is_locked("tenant-b"))
            forget_all("tenant-a")
            self.assertFalse(has_pin("tenant-a"))
            # Tenant-b stays.
            self.assertTrue(has_pin("tenant-b"))

    # ------------------------------------------------------------------ #
    # 6. No stripe token in core/
    # ------------------------------------------------------------------ #

    def test_no_stripe_in_core(self) -> None:
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
    # 7. No face/voice enrollment in core/
    # ------------------------------------------------------------------ #

    def test_no_face_voice_enrollment_in_core(self) -> None:
        """core/ source files contain no face/voice enrollment strings."""
        core_dir = Path(__file__).resolve().parent.parent / "core"
        for p in core_dir.glob("*.py"):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("face id", text, f"face id in {p.name}")
            self.assertNotIn("faceid", text, f"faceid in {p.name}")
            self.assertNotIn("voice id", text, f"voice id in {p.name}")
            self.assertNotIn("voiceid", text, f"voiceid in {p.name}")
            self.assertNotIn("enrollment", text, f"enrollment in {p.name}")

    # ------------------------------------------------------------------ #
    # 8. Both app.html copies stay byte-sync
    # ------------------------------------------------------------------ #

    def test_app_html_copies_byte_sync(self) -> None:
        """Both app.html copies are byte-identical."""
        repo = Path(__file__).resolve().parent.parent
        a = (repo / "app.html").read_bytes()
        b = (
            repo
            / "desktop"
            / "macos"
            / "Aegis.app"
            / "Contents"
            / "Resources"
            / "app.html"
        ).read_bytes()
        self.assertEqual(a, b, "app.html and desktop copy are not byte-sync")

    # ------------------------------------------------------------------ #
    # 9. touch_id_available / unlock_with_touch_id typed responses
    # ------------------------------------------------------------------ #

    def test_mock_unavailable_typed(self) -> None:
        """mock_unavailable is a typed deny — stays locked."""
        from core.session_lock import (
            is_locked,
            lock,
            set_pin,
            touch_id_available,
            unlock_with_touch_id,
        )

        os.environ["AEGIS_TOUCH_ID_MOCK_AVAILABLE"] = "0"
        with mock.patch(
            "core.session_lock.get_store", return_value=self._mock_keychain()
        ):
            set_pin("tenant-a", "123456")
            lock("tenant-a")
            self.assertFalse(touch_id_available())
            result = unlock_with_touch_id("tenant-a")
            self.assertFalse(result["unlocked"])
            self.assertEqual(result["code"], "TOUCH_ID_UNAVAILABLE")
            self.assertTrue(is_locked("tenant-a"))


if __name__ == "__main__":
    unittest.main()
