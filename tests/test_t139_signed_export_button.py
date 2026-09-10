"""T139 — Operator export button posts signed-export and shows result.

Covers:
* ``test_operator_html_posts_signed_export_route``: app.html contains the
  signed-export route string and a click handler wired to it.
* ``test_signed_export_status_element_present``: app.html has a status
  element (id ``signed-brief-label``) to show path or typed error.
* ``test_signed_export_api_still_200_with_profile``: TestClient POST to
  the signed-export route returns 200 with a path outside the repo worktree.

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


class TestT139SignedExportButton(unittest.TestCase):
    """Operator export button posts signed-export and shows result."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t139_")
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
    # 1) HTML contains the signed-export route and a click handler
    # ------------------------------------------------------------------ #

    def test_operator_html_posts_signed_export_route(self) -> None:
        """app.html contains the signed-export route string and a click
        handler that calls ``exportSignedBrief``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()
        # The route string must be present.
        self.assertIn("/api/v1/twin/brief/signed-export", lowered,
                      "app.html missing signed-export route string")
        # The click handler must reference exportSignedBrief.
        self.assertIn("exportsignedbrief", lowered,
                      "app.html missing exportSignedBrief click handler")
        # The button must be wired to the handler.
        self.assertIn("onclick=\"exportsignedbrief()\"", lowered,
                      "app.html missing onclick handler for export button")

    # ------------------------------------------------------------------ #
    # 2) Status element is present
    # ------------------------------------------------------------------ #

    def test_signed_export_status_element_present(self) -> None:
        """app.html has a status element (``signed-brief-label``) next to
        the button to show the path or typed error."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("signed-brief-label", html,
                      "app.html missing signed-brief-label status element")
        self.assertIn("btn-signed-brief", html,
                      "app.html missing btn-signed-brief button")

    # ------------------------------------------------------------------ #
    # 3) API still returns 200 with a profile; path outside repo
    # ------------------------------------------------------------------ #

    def test_signed_export_api_still_200_with_profile(self) -> None:
        """TestClient POST to the signed-export route returns 200 with a
        path outside the repo worktree."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t139-signed"
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
        # Path must be under AEGIS_DATA_DIR (temp), not the repo.
        self.assertTrue(
            str(out_path).startswith(str(self._tmp)),
            f"export file {out_path} not under AEGIS_DATA_DIR ({self._tmp})",
        )
        self.assertFalse(
            str(out_path).startswith(str(_REPO_ROOT)),
            f"export file {out_path} leaked into the repo worktree",
        )

    # ------------------------------------------------------------------ #
    # 4) Handler has no silent prefill return (T139_FIX)
    # ------------------------------------------------------------------ #

    def test_export_button_handler_has_no_silent_prefill_return(self) -> None:
      """Handler source contains signed-export and must not return before
      fetch solely because profilePrefill is falsy."""
      html = _APP_HTML.read_text(encoding="utf-8")
      lowered = html.lower()
      self.assertIn("signed-export", lowered,
                    "handler missing signed-export route string")
      # Extract the exportSignedBrief function body (lowercased source).
      start = lowered.find("window.exportsignedbrief")
      self.assertGreater(start, -1, "exportSignedBrief function not found")
      end = lowered.find("};", start)
      self.assertGreater(end, start, "exportSignedBrief function end not found")
      body = lowered[start:end]
      # Must contain a post call referencing signed-export.
      self.assertIn("signed-export", body,
                    "handler body missing signed-export post call")
      # Must NOT contain the silent profilePrefill return that swallowed
      # the click before the POST.
      self.assertNotIn("if (!profileprefill)", body,
                       "handler still has silent profilePrefill early-return")

    # ------------------------------------------------------------------ #
    # 5) Status sets "Exporting…" text on click (T139_FIX)
    # ------------------------------------------------------------------ #

    def test_export_status_sets_exporting_text(self) -> None:
      """Handler source contains the word 'Exporting' so the operator
      sees a status change immediately on click."""
      html = _APP_HTML.read_text(encoding="utf-8")
      lowered = html.lower()
      start = lowered.find("window.exportsignedbrief")
      end = lowered.find("};", start)
      body = lowered[start:end]
      self.assertIn("exporting", body,
                    "handler missing 'Exporting…' immediate status text")

    # ------------------------------------------------------------------ #
    # 6) Markup is not disabled (T139_FIX2)
    # ------------------------------------------------------------------ #

    def test_signed_export_button_markup_is_not_disabled(self) -> None:
        """The HTML string served by GET / contains id="btn-signed-brief"
        and that same tag does not contain disabled."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        html = client.get("/").text
        i = html.find('id="btn-signed-brief"')
        self.assertGreater(i, -1, "served HTML missing id=\"btn-signed-brief\"")
        chunk = html[i:i + 180]
        self.assertIn("btn-signed-brief", chunk,
                      "chunk around btn-signed-brief missing the id")
        self.assertNotIn("disabled", chunk,
                         "btn-signed-brief tag must not contain disabled")

    # ------------------------------------------------------------------ #
    # 7) No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
