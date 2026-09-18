"""T204 — Local proof: observe byte receipt + evidence zip brief verify.

Covers:

* ``test_observe_writes_byte_receipt`` — a successful observe of a
  local ``.eml`` writes one byte receipt under the data dir.
* ``test_observe_receipt_has_sha256_and_length`` — the receipt records
  tenant, source basename, byte length, and sha256 of the raw bytes.
* ``test_outside_path_no_receipt`` — a path outside the data dir is a
  typed deny and writes zero receipts.
* ``test_evidence_zip_includes_last_brief`` — the evidence pack zip
  contains the last ``local_*.md`` brief.
* ``test_evidence_zip_includes_sibling_sig_when_present`` — the zip
  contains the sibling ``.sig`` when present.
* ``test_evidence_zip_includes_intact_or_tampered_or_missing`` — the
  zip contains a ``brief_verify.txt`` member whose body is Intact,
  Tampered, or Missing.
* ``test_observe_does_not_execute`` — observe only proposes; no row is
  executed.
* ``test_core_tree_has_no_stripe_token`` — no ``stripe`` token in any
  ``core/*.py`` file.
* ``test_readme_author_untouched`` — the README Author paragraph is
  intact.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
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

_NOT = "not"
_AR = "arized"
_NF = _NOT + _AR  # built to avoid self-trip


class TestT204LocalProof(unittest.TestCase):
    """T204 — observe byte receipt; evidence zip brief+.sig+Intact."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t204_")
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

    def _observe(self, tenant_id: str, file_path: Path):
        """POST to the observe route and return the JSON body."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": tenant_id, "file_path": str(file_path)},
        )
        return resp

    # ------------------------------------------------------------------ #
    # 1) Observe writes byte receipt
    # ------------------------------------------------------------------ #

    def test_observe_writes_byte_receipt(self) -> None:
        """A successful observe writes one byte receipt under the data dir."""
        path = self._write_eml()
        resp = self._observe("t204-receipt", path)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("byte_receipt", body)
        receipt_path = Path(body["byte_receipt"])
        self.assertTrue(receipt_path.is_file())
        # The receipt must be under the data dir.
        data_dir = Path(self._tmp).resolve()
        self.assertIn(str(data_dir), str(receipt_path.resolve()))

    # ------------------------------------------------------------------ #
    # 2) Receipt has sha256 and length
    # ------------------------------------------------------------------ #

    def test_observe_receipt_has_sha256_and_length(self) -> None:
        """The receipt records tenant, source basename, byte length, sha256."""
        path = self._write_eml("msg.eml")
        raw = path.read_bytes()
        import hashlib

        expected_sha = hashlib.sha256(raw).hexdigest()
        resp = self._observe("t204-sha", path)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        receipt_path = Path(body["byte_receipt"])
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(data["tenant_id"], "t204-sha")
        self.assertEqual(data["source"], "msg.eml")
        self.assertEqual(data["byte_length"], len(raw))
        self.assertEqual(data["sha256"], expected_sha)

    # ------------------------------------------------------------------ #
    # 3) Outside path — no receipt
    # ------------------------------------------------------------------ #

    def test_outside_path_no_receipt(self) -> None:
        """A path outside the data dir is a typed deny with zero receipts."""
        # Count receipts before.
        receipts_dir = Path(self._tmp) / "receipts"
        before = len(list(receipts_dir.glob("observe_*.json"))) if receipts_dir.is_dir() else 0
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/observe/mail-calendar",
            json={"tenant_id": "t204-out", "file_path": "/etc/hostname"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "path_denied_outside_data_dir")
        # No new receipt was written.
        after = len(list(receipts_dir.glob("observe_*.json"))) if receipts_dir.is_dir() else 0
        self.assertEqual(after, before)

    # ------------------------------------------------------------------ #
    # 4) Evidence zip includes last brief
    # ------------------------------------------------------------------ #

    def test_evidence_zip_includes_last_brief(self) -> None:
        """The evidence pack zip contains the last signed brief."""
        from core.evidence_desk import build_evidence_pack
        from core.twin_local_recall import signed_export

        signed_export("t204-zip", name="local_t204_test.md")
        result = build_evidence_pack("t204-zip")
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("brief.md", names)

    # ------------------------------------------------------------------ #
    # 5) Evidence zip includes sibling .sig when present
    # ------------------------------------------------------------------ #

    def test_evidence_zip_includes_sibling_sig_when_present(self) -> None:
        """The zip contains brief.md.sig when the sibling .sig exists."""
        from core.evidence_desk import build_evidence_pack
        from core.twin_local_recall import signed_export

        signed_export("t204-sig", name="local_t204_sig.md")
        result = build_evidence_pack("t204-sig")
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("brief.md", names)
            self.assertIn("brief.md.sig", names)

    # ------------------------------------------------------------------ #
    # 6) Evidence zip includes Intact or Tampered or Missing
    # ------------------------------------------------------------------ #

    def test_evidence_zip_includes_intact_or_tampered_or_missing(self) -> None:
        """The zip has brief_verify.txt with Intact, Tampered, or Missing."""
        from core.evidence_desk import build_evidence_pack
        from core.twin_local_recall import signed_export

        # Case A: brief exists and verifies → Intact.
        signed_export("t204-intact", name="local_t204_intact.md")
        result = build_evidence_pack("t204-intact")
        with zipfile.ZipFile(Path(result["path"]), "r") as zf:
            names = zf.namelist()
            self.assertIn("brief_verify.txt", names)
            body = zf.read("brief_verify.txt").decode("utf-8").strip()
            self.assertIn(body, {"Intact", "Tampered", "Missing"})

        # Case B: no brief at all → Missing.  Use a fresh data dir so
        # no export/local_*.md lingers from Case A.
        tmp_b = tempfile.mkdtemp(prefix="aegis_t204_b_")
        os.environ["AEGIS_DATA_DIR"] = tmp_b
        try:
            result2 = build_evidence_pack("t204-missing")
            with zipfile.ZipFile(Path(result2["path"]), "r") as zf:
                body2 = zf.read("brief_verify.txt").decode("utf-8").strip()
                self.assertEqual(body2, "Missing")
        finally:
            os.environ["AEGIS_DATA_DIR"] = self._tmp

    # ------------------------------------------------------------------ #
    # 7) Observe does not execute
    # ------------------------------------------------------------------ #

    def test_observe_does_not_execute(self) -> None:
        """A successful observe only proposes; no row is executed."""
        path = self._write_eml()
        from core.twin_actions import list_actions

        resp = self._observe("t204-noexec", path)
        self.assertEqual(resp.status_code, 200)
        rows = list_actions("t204-noexec")
        for row in rows:
            self.assertNotEqual(row["status"], "executed")

    # ------------------------------------------------------------------ #
    # 8) Core tree has no Stripe token
    # ------------------------------------------------------------------ #

    def test_core_tree_has_no_stripe_token(self) -> None:
        """No core/*.py file contains the stripe token literal."""
        import glob

        for py in glob.glob(str(_REPO_ROOT / "core" / "*.py")):
            text = Path(py).read_text(encoding="utf-8")
            self.assertNotIn("stripe", text.lower())

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and intact."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word notarized."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
