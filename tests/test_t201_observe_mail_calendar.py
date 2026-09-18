"""T201 — Observe-only local mail/calendar propose.

Covers:

* ``test_html_has_observe_local_control`` — the operator page has the
  ``btn-observe-mail`` control and the ``observe-mail-label`` span.
* ``test_eml_inside_data_dir_proposes`` — a valid ``.eml`` file inside
  ``AEGIS_DATA_DIR`` produces six proposed cards with status
  ``proposed``.
* ``test_ics_inside_data_dir_proposes`` — a valid ``.ics`` file inside
  ``AEGIS_DATA_DIR`` produces six proposed cards with status
  ``proposed``.
* ``test_outside_data_dir_typed_deny`` — a path outside the data dir is
  a typed deny (``path_denied_outside_data_dir``).
* ``test_send_effect_typed_deny`` — the ``send`` effect (and its peers)
  is a typed deny — ``denied_effects()`` returns the frozenset and the
  module never proposes or executes it.
* ``test_observe_does_not_execute`` — a successful observe only
  proposes; no row has status ``executed``.
* ``test_missing_file_typed_fail`` — a path inside the data dir that
  does not exist is a typed fail (``observe_denied``).
* ``test_wrong_suffix_typed_fail`` — a file inside the data dir with a
  non-``.eml``/``.ics`` suffix is a typed fail (``observe_denied``).
* ``test_readme_author_untouched`` — the README Author paragraph is
  intact.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)
_README = _REPO_ROOT / "README.md"

_NF = "not" + "arized"  # built at runtime to avoid self-trip


class TestT201ObserveMailCalendar(unittest.TestCase):
    """Observe-only local .eml/.ics propose; send is a typed deny."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t201_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _write_eml(self, name: str = "sample.eml") -> Path:
        """Write a minimal valid ``.eml`` inside the data dir."""
        path = Path(self._tmp) / name
        path.write_text(
            "From: alice@example.com\r\n"
            "Subject: Weekly sync\r\n"
            "\r\n"
            "Team, the weekly sync is confirmed for Friday.\r\n",
            encoding="utf-8",
        )
        return path

    def _write_ics(self, name: str = "sample.ics") -> Path:
        """Write a minimal valid ``.ics`` inside the data dir."""
        path = Path(self._tmp) / name
        path.write_text(
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Team standup\r\n"
            "DTSTART:20260918T090000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------------ #
    # 1) HTML has observe local control
    # ------------------------------------------------------------------ #
    def test_html_has_observe_local_control(self) -> None:
        """The operator page has ``btn-observe-mail`` and the label span."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("btn-observe-mail", html)
        self.assertIn("observe-mail-label", html)
        self.assertIn("observeMailCalendar", html)

    # ------------------------------------------------------------------ #
    # 2) .eml inside data dir proposes
    # ------------------------------------------------------------------ #
    def test_eml_inside_data_dir_proposes(self) -> None:
        """A valid ``.eml`` inside the data dir proposes six cards."""
        path = self._write_eml()
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t201-eml", "file_path": str(path)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 6)
        proposed = body["proposed"]
        self.assertEqual(len(proposed), 6)
        for row in proposed:
            self.assertEqual(row["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 3) .ics inside data dir proposes
    # ------------------------------------------------------------------ #
    def test_ics_inside_data_dir_proposes(self) -> None:
        """A valid ``.ics`` inside the data dir proposes six cards."""
        path = self._write_ics()
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t201-ics", "file_path": str(path)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 6)
        for row in body["proposed"]:
            self.assertEqual(row["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 4) Outside data dir — typed deny
    # ------------------------------------------------------------------ #
    def test_outside_data_dir_typed_deny(self) -> None:
        """A path outside the data dir is a typed deny."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t201-out", "file_path": "/etc/hostname"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "path_denied_outside_data_dir")

    # ------------------------------------------------------------------ #
    # 5) Send effect is a typed deny
    # ------------------------------------------------------------------ #
    def test_send_effect_typed_deny(self) -> None:
        """The ``send`` effect (and its peers) is a typed deny."""
        from core.observe_mail_calendar import denied_effects

        effects = denied_effects()
        self.assertIn("send", effects)
        self.assertIn("smtp", effects)
        self.assertIn("mailto", effects)
        self.assertIn("calendar-write", effects)
        self.assertIn("invite-send", effects)
        # The observe module must never propose or execute a send.
        # Source-level guard: no execute call in the module.
        src = (
            _REPO_ROOT
            / "core"
            / "observe_mail_calendar.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(".execute(", src)
        self.assertNotIn("twin_actions.execute", src)

    # ------------------------------------------------------------------ #
    # 6) Observe does not execute
    # ------------------------------------------------------------------ #
    def test_observe_does_not_execute(self) -> None:
        """A successful observe only proposes; no row is executed."""
        path = self._write_eml()
        from core.twin_actions import list_actions

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t201-noexec", "file_path": str(path)},
        )
        self.assertEqual(resp.status_code, 200)
        rows = list_actions("t201-noexec")
        for row in rows:
            self.assertNotEqual(row["status"], "executed")

    # ------------------------------------------------------------------ #
    # 7) Missing file — typed fail
    # ------------------------------------------------------------------ #
    def test_missing_file_typed_fail(self) -> None:
        """A path inside the data dir that does not exist is a typed fail."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={
                "tenant_id": "t201-missing",
                "file_path": str(Path(self._tmp) / "nope.eml"),
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "observe_denied")

    # ------------------------------------------------------------------ #
    # 8) Wrong suffix — typed fail
    # ------------------------------------------------------------------ #
    def test_wrong_suffix_typed_fail(self) -> None:
        """A file with a non-``.eml``/``.ics`` suffix is a typed fail."""
        path = Path(self._tmp) / "notes.txt"
        path.write_text("hello", encoding="utf-8")
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t201-suffix", "file_path": str(path)},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "observe_denied")

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
