"""T115 — Truth surfaces, local privacy model, SQLite durability proof.

Covers:
- docs/PRIVACY_MODEL.md exists and is honest (AEGIS_DATA_DIR, Echo, no
  Stripe, payment mentioned).
- STATUS.md names the six agents.
- README.md keeps both brand strings and the Author paragraph.
- A profile written via the existing SQLite store survives reopening a
  new store against the same AEGIS_DATA_DIR.
- No live network except TestClient.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_interview import QUESTIONS, TwinInterviewStore

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT115PrivacyDurability(unittest.TestCase):
    """Honest privacy-model and local-durability invariants."""

    # ------------------------------------------------------------------ #
    # docs / truth surfaces
    # ------------------------------------------------------------------ #

    def test_privacy_model_file_exists(self) -> None:
        """docs/PRIVACY_MODEL.md exists and is non-empty."""
        path = _REPO_ROOT / "docs" / "PRIVACY_MODEL.md"
        self.assertTrue(path.exists(), "docs/PRIVACY_MODEL.md must exist")
        self.assertGreater(len(path.read_text()), 100)

    def test_privacy_model_forbids_psp_in_core(self) -> None:
        """Privacy model names AEGIS_DATA_DIR + Echo and forbids Stripe in core."""
        text = (_REPO_ROOT / "docs" / "PRIVACY_MODEL.md").read_text()
        self.assertIn("AEGIS_DATA_DIR", text)
        self.assertIn("Echo", text)
        self.assertNotIn("Stripe", text)
        self.assertIn("payment", text.lower())

    def test_status_names_six_agents(self) -> None:
        """STATUS.md mentions all six specialist names."""
        text = (_REPO_ROOT / "STATUS.md").read_text()
        for name in ("Bita", "Kian", "Alina", "Aylin", "Ahmad", "Amin"):
            self.assertIn(name, text, f"STATUS.md missing agent {name!r}")

    def test_readme_author_brands_intact(self) -> None:
        """README keeps both brand strings and the Author paragraph."""
        text = (_REPO_ROOT / "README.md").read_text()
        self.assertIn("AI Architect Amin Azimi — End-to-End System Development", text)
        self.assertIn("Azimi Innovation Lab", text)
        self.assertIn("## Author", text)

    # ------------------------------------------------------------------ #
    # SQLite durability — profile survives reopening a new store
    # ------------------------------------------------------------------ #

    def test_sqlite_profile_survives_reopen(self) -> None:
        """Write a profile, open a *new* store against the same data dir,
        and read the profile back — the SQLite file on disk is the source
        of truth, not in-memory state."""
        tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = tmp
        try:
            tenant = "t115dur"
            store_a = TwinInterviewStore()
            session = store_a.start_session(tenant)
            sid = session["session_id"]
            for q in QUESTIONS:
                store_a.answer(sid, q["id"], f"ans-{q['id']}")
            row = store_a.commit(sid, True)
            self.assertEqual(row["tenant_id"], tenant)

            # Simulate "close the client" by dropping the reference; the
            # data lives in the SQLite file, not in the object.
            del store_a

            # Open a *new* store against the same AEGIS_DATA_DIR.
            store_b = TwinInterviewStore()
            reopened = store_b.get_latest_profile(tenant)
            self.assertIsNotNone(reopened, "profile must survive store reopen")
            assert reopened is not None  # for the type checker
            self.assertEqual(reopened["tenant_id"], tenant)
            self.assertTrue(reopened["consent"])
        finally:
            os.environ.pop("AEGIS_DATA_DIR", None)


if __name__ == "__main__":
    unittest.main()
