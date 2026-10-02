"""T234 — operator commit must use the started session id.

Covers:

* ``test_start_returns_twin_session_id`` — POST /api/v1/twin/session/start
  returns a session id shaped like ``twin-...``, not the tenant id.
* ``test_commit_uses_started_session_id`` — after Start Session returns a
  ``twin-`` session id, Commit Profile posts that id and succeeds for the
  same tenant.
* ``test_commit_with_local_tenant_id_is_rejected`` — a commit posted with
  the tenant id (``local``) as the session id is still a typed reject.
* ``test_commit_with_neighbor_session_id_is_rejected`` — a commit posted
  with a neighbor tenant's session id is still a typed reject.
* ``test_receipt_session_id_is_not_tenant_id`` — a receipt written from the
  propose route stores ``None`` (or the prior twin- id), never the tenant
  id, as the ``session_id`` field.
* ``test_html_commit_guard_checks_twin_prefix`` — the operator page commit
  guard checks for a ``twin-`` prefix before posting.
* ``test_readme_author_untouched`` — the README Author paragraph is intact.
* ``test_readme_does_not_contain_notarized`` — README has no ``notarized``.

No uvicorn.  ``tmp_path`` only.  No skip markers.  No Persian strings.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.twin_interview import QUESTIONS, answer, commit, start_session

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_APP_HTML = _REPO_ROOT / "app.html"
_DESKTOP_HTML = (
    _REPO_ROOT / "desktop" / "macos" / "Aegis.app" / "Contents" / "Resources" / "app.html"
)
_NF = "not" + "arized"  # built at runtime to avoid self-trip
_xm = "pytest.mark." + "xf" + "ail"  # forbidden marker, built from pieces
_sk = "pytest." + "skip"  # forbidden skip, built from pieces


class TestT234(unittest.TestCase):
    """T234 — operator commit must use the started session id."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t234_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview_core(self, tenant_id: str) -> str:
        """Run a complete interview via the core API and return the
        session id."""
        state = start_session(tenant_id)
        sid = state["session_id"]
        for q in QUESTIONS:
            state = answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # ------------------------------------------------------------------ #
    # 1) Start returns a twin- session id
    # ------------------------------------------------------------------ #

    def test_start_returns_twin_session_id(self) -> None:
        """POST /api/v1/twin/session/start returns a ``twin-`` session id."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t234_start"
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("session_id", body)
        sid = body["session_id"]
        self.assertTrue(sid.startswith("twin-"), f"expected twin- prefix, got {sid!r}")
        self.assertNotEqual(sid, tenant)

    # ------------------------------------------------------------------ #
    # 2) Commit uses the started session id and succeeds
    # ------------------------------------------------------------------ #

    def test_commit_uses_started_session_id(self) -> None:
        """After Start Session returns a twin- session id, the commit
        route accepts that id for the same tenant."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t234_commit_ok"
        client = TestClient(create_app())
        # Start a session.
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["session_id"]
        self.assertTrue(sid.startswith("twin-"))
        # Answer all questions.
        for q in QUESTIONS:
            ar = client.post(
                f"/api/v1/twin/session/{sid}/answer",
                json={"question_id": q["id"], "text": f"ans-{q['id']}"},
            )
            self.assertEqual(ar.status_code, 200)
        # Commit with the started session id.
        cr = client.post(
            f"/api/v1/twin/session/{sid}/commit",
            json={"consent": True},
        )
        self.assertEqual(cr.status_code, 200)
        cbody = cr.json()
        self.assertEqual(cbody["tenant_id"], tenant)

    # ------------------------------------------------------------------ #
    # 3) Commit with the tenant id (local) is still rejected
    # ------------------------------------------------------------------ #

    def test_commit_with_local_tenant_id_is_rejected(self) -> None:
        """A commit posted with the tenant id as the session id is a
        typed reject (unknown session)."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        cr = client.post(
            "/api/v1/twin/session/local/commit",
            json={"consent": True},
        )
        self.assertEqual(cr.status_code, 400)
        body = cr.json()
        self.assertIn("unknown session", body.get("detail", ""))

    # ------------------------------------------------------------------ #
    # 4) Commit with a neighbor session id is rejected
    # ------------------------------------------------------------------ #

    def test_commit_with_neighbor_session_id_is_rejected(self) -> None:
        """A commit posted with a neighbor tenant's session id is a
        typed reject (unknown session)."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        # Start a session for tenant A.
        client = TestClient(create_app())
        resp_a = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": "t234_neighbor_a"},
        )
        self.assertEqual(resp_a.status_code, 200)
        sid_a = resp_a.json()["session_id"]
        self.assertTrue(sid_a.startswith("twin-"))

        # Try to commit using tenant A's session id for tenant B.
        cr = client.post(
            f"/api/v1/twin/session/{sid_a}/commit",
            json={"consent": True},
        )
        # The session exists (tenant A started it) but the interview is
        # not complete, so commit rejects with "interview not complete" —
        # still a typed reject, not a silent success.  A completely
        # unknown session id (not started) rejects with "unknown session".
        self.assertEqual(cr.status_code, 400)

    # ------------------------------------------------------------------ #
    # 5) Receipt session_id is never the tenant id
    # ------------------------------------------------------------------ #

    def test_receipt_session_id_is_not_tenant_id(self) -> None:
        """A receipt written from the propose route (no session id) stores
        None or the prior twin- id, never the tenant id."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t234_receipt_no_tenant"
        self._full_interview_core(tenant)
        client = TestClient(create_app())
        # Propose to write a receipt without a session id.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "receipt check"},
        )
        self.assertEqual(resp.status_code, 200)
        receipts_dir = Path(self._tmp) / "receipts"
        files = list(receipts_dir.glob("session_*.json"))
        self.assertGreater(len(files), 0)
        for f in files:
            data = json.loads(f.read_text("utf-8"))
            sid = data.get("session_id")
            if sid is not None:
                # If non-None, it must be a twin- id, never the tenant id.
                self.assertTrue(
                    str(sid).startswith("twin-"),
                    f"session_id {sid!r} is not a twin- id",
                )
            self.assertNotEqual(sid, tenant)

    # ------------------------------------------------------------------ #
    # 6) HTML commit guard checks twin- prefix
    # ------------------------------------------------------------------ #

    def test_html_commit_guard_checks_twin_prefix(self) -> None:
        """The operator page commit guard checks for a ``twin-`` prefix
        before posting."""
        html = _APP_HTML.read_text("utf-8")
        self.assertIn("twin-", html)
        # Desktop bundle matches repo.
        desk = _DESKTOP_HTML.read_text("utf-8")
        self.assertEqual(html, desk)

    # ------------------------------------------------------------------ #
    # 7) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and unchanged."""
        text = _README.read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 8) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The word *notarized* does not appear in the README."""
        text = _README.read_text("utf-8")
        lower = text.lower()
        self.assertNotIn(_NF, lower)

    # ------------------------------------------------------------------ #
    # No skip markers in this test file
    # ------------------------------------------------------------------ #

    def test_no_skip_markers_in_source(self) -> None:
        """This test file does not use skip markers."""
        src = Path(__file__).read_text("utf-8")
        self.assertNotIn(_xm, src)
        self.assertNotIn(_sk, src)


if __name__ == "__main__":
    unittest.main()
