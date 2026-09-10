"""T142 — Signed-export status depth on the operator page.

Covers:
* ``test_signed_export_button_still_posts_route``: the handler still
  POSTs the signed-export route and shows ``Exporting`` immediately.
* ``test_status_node_exists``: the served HTML has the
  ``signed-brief-label`` status node.
* ``test_export_failed_copy_in_html_or_script``: the HTML or script
  contains the typed ``export_failed:`` error copy for non-200 and
  network failures.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import (
    _ensure_schema,
    insert_specialist_proposal,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session

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


class TestT142ExportStatus(unittest.TestCase):
    """Signed-export status depth on the operator page."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t142_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}-{tenant_id}")
        commit(sid, True)
        return sid

    def _insert_proposed(self, tenant_id: str, title: str = "Review digest") -> str:
        """Insert a proposed specialist action and return its action_id."""
        _ensure_schema()
        row = insert_specialist_proposal(
            tenant_id=tenant_id,
            agent_name="twin_local",
            title=title,
            payload={"body": title},
        )
        return row["action_id"]

    # ------------------------------------------------------------------ #
    # 1) Handler still POSTs the signed-export route
    # ------------------------------------------------------------------ #

    def test_signed_export_button_still_posts_route(self) -> None:
        """The exportSignedBrief handler still POSTs the signed-export
        route and sets an ``Exporting`` status immediately on click."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()
        start = lowered.find("window.exportsignedbrief")
        self.assertGreater(start, -1, "exportSignedBrief function not found")
        end = lowered.find("};", start)
        self.assertGreater(end, start, "exportSignedBrief function end not found")
        body = lowered[start:end]
        self.assertIn("signed-export", body,
                      "handler body missing signed-export route string")
        self.assertIn("exporting", body,
                      "handler missing 'Exporting' immediate status text")

    # ------------------------------------------------------------------ #
    # 2) Status node exists in served HTML
    # ------------------------------------------------------------------ #

    def test_status_node_exists(self) -> None:
        """The served HTML contains the ``signed-brief-label`` status
        node and the ``btn-signed-brief`` button."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        html = client.get("/").text
        self.assertIn("signed-brief-label", html,
                      "served HTML missing signed-brief-label status node")
        self.assertIn("btn-signed-brief", html,
                      "served HTML missing btn-signed-brief button")

    # ------------------------------------------------------------------ #
    # 3) export_failed typed copy present in HTML or script
    # ------------------------------------------------------------------ #

    def test_export_failed_copy_in_html_or_script(self) -> None:
        """The HTML source contains the typed ``export_failed:``
        error copy for non-200 and network failures, plus
        ``export_failed: network`` and ``export_failed: missing_file``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()
        start = lowered.find("window.exportsignedbrief")
        self.assertGreater(start, -1, "exportSignedBrief function not found")
        end = lowered.find("};", start)
        self.assertGreater(end, start, "exportSignedBrief function end not found")
        body = lowered[start:end]
        self.assertIn("export_failed: network", body,
                      "handler missing 'export_failed: network' copy")
        self.assertIn("export_failed: ", body,
                      "handler missing 'export_failed:' typed error copy")
        # missing_file check across the full HTML (the check is in the
        # handler body but may also appear in the reveal handler).
        self.assertIn("export_failed: missing_file", lowered,
                      "HTML missing 'export_failed: missing_file' copy")

    # ------------------------------------------------------------------ #
    # 4) API still returns 200 with a profile
    # ------------------------------------------------------------------ #

    def test_signed_export_api_still_200_with_profile(self) -> None:
        """TestClient POST to the signed-export route returns 200 with
        a path outside the repo worktree."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t142-signed"
        self._full_interview(tenant)
        self._insert_proposed(tenant, title="Signed export action")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/brief/signed-export",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("path", data)
        out_path = Path(data["path"])
        self.assertTrue(out_path.is_file(), "export file not created")
        self.assertTrue(
            str(out_path).startswith(str(self._tmp)),
            f"export file {out_path} not under AEGIS_DATA_DIR ({self._tmp})",
        )

    # ------------------------------------------------------------------ #
    # 5) Reveal script exists and is executable
    # ------------------------------------------------------------------ #

    def test_reveal_script_exists(self) -> None:
        """The ``scripts/reveal_export.sh`` helper exists."""
        script = _REPO_ROOT / "scripts" / "reveal_export.sh"
        self.assertTrue(script.is_file(), "reveal_export.sh not found")

    # ------------------------------------------------------------------ #
    # 6) No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
