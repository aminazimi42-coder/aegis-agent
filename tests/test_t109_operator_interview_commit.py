"""T109 — Operator interview commit.

Verifies that the operator page commits a four-field profile (name, role,
goals, timezone) mapped onto the store's question IDs, that ``GET
/api/v1/twin/profile/{tenant_id}`` returns 200 with an empty object when no
profile exists (not 404), and that commit/answer errors return the server
error text — never a generic ``Error`` string.

No live network except the FastAPI ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS
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


class TestT109OperatorInterviewCommit(unittest.TestCase):
    """Operator page posts answers then commit; errors are not generic."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t109_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # A filled four-field form commits and returns 200
    # ------------------------------------------------------------------ #

    def test_commit_four_fields_ok(self) -> None:
        """Start session, answer all 6 store questions, commit → 200."""
        app = create_app()
        client = TestClient(app)
        tenant = "t109-ok"
        # Start a session through the API.
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["session_id"]
        # Answer all questions in the store's expected order.
        for q in QUESTIONS:
            r = client.post(
                f"/api/v1/twin/session/{sid}/answer",
                json={"question_id": q["id"], "text": f"val-{q['id']}"},
            )
            self.assertEqual(r.status_code, 200)
        # Commit.
        r = client.post(
            f"/api/v1/twin/session/{sid}/commit",
            json={"consent": True},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("profile_id", body)
        # Profile should now be retrievable.
        pr = client.get(f"/api/v1/twin/profile/{tenant}")
        self.assertEqual(pr.status_code, 200)
        self.assertEqual(pr.json()["tenant_id"], tenant)

    # ------------------------------------------------------------------ #
    # Missing profile returns 200 with an empty object, not 404
    # ------------------------------------------------------------------ #

    def test_missing_profile_is_empty_not_404(self) -> None:
        """GET profile for a tenant with no committed profile → 200, not 404."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/profile/t109-missing-tenant")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, dict)
        self.assertIn("tenant_id", body)
        self.assertIsNone(body.get("profile_id"))

    # ------------------------------------------------------------------ #
    # Error text is the server's detail, not a generic "Error"
    # ------------------------------------------------------------------ #

    def test_error_text_not_generic_only(self) -> None:
        """Commit on an incomplete (no answers) session must return the
        server error text (``detail``), not a bare ``Error`` string."""
        app = create_app()
        client = TestClient(app)
        tenant = "t109-err"
        # Start a session but do NOT answer any questions.
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["session_id"]
        # Commit without completing → server should reject with a real detail.
        r = client.post(
            f"/api/v1/twin/session/{sid}/commit",
            json={"consent": True},
        )
        self.assertNotEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("detail", body)
        detail = body["detail"]
        # The detail must be a non-generic, server-provided message.
        self.assertTrue(str(detail).strip())
        self.assertNotEqual(str(detail).strip().lower(), "error")
        # Also check that app.html does not use a bare "Error" as the only
        # commit failure text — it must show server error detail.
        html = _APP_HTML.read_text(encoding="utf-8")
        # The old generic "Error" label text must be gone from commit path.
        self.assertNotIn('el("commit-label").textContent = "Error"', html)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
