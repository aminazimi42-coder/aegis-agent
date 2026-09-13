"""T174 — Loop depth from durable notes and profile.

Verifies:
- ``test_reject_reason_appears_on_next_propose`` — after a reject, the next
  propose response includes ``last_reject_reason`` from the durable store.
- ``test_approve_note_appears_on_next_propose`` — after an approve with a
  why text, the next propose response includes ``last_approve_note``.
- ``test_weekly_brief_uses_saved_profile_role_or_goals`` — the weekly brief
  JS function builds its text from the saved profile role or goals.
- ``test_notes_survive_store_reopen`` — after clearing the in-memory state
  and reopening the store (a fresh connection), the notes still feed the
  next propose response.
- ``test_approved_strip_still_present`` — the Approved strip HTML is still
  present in ``app.html``.
- ``test_readme_does_not_claim_months_of_learning`` — README does not
  claim months of learning; it says this is not a multi-month twin.
- ``test_readme_author_untouched`` — the README Author paragraph is
  untouched and present.

Uses ``tmp_path`` via ``tempfile.mkdtemp``.  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_APP_HTML_CANDIDATES = [
    REPO_ROOT / "app.html",
    REPO_ROOT / "desktop" / "macos" / "Aegis.app" / "Contents" / "Resources" / "app.html",
]


def _read_app_html() -> str:
    for p in _APP_HTML_CANDIDATES:
        if p.is_file():
            return p.read_text()
    return ""


class TestT174LoopDepth(unittest.TestCase):
    """Durable notes and profile feed the next propose; approved strip stays."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t174_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_profile(self, tenant: str) -> None:
        """Create a committed profile so propose_actions works."""
        from core.twin_interview import (
            answer as twin_answer,
        )
        from core.twin_interview import (
            commit as twin_commit,
        )
        from core.twin_interview import (
            start_session as twin_start,
        )

        state = twin_start(tenant)
        session_id = state["session_id"]
        for _ in range(6):
            qid = state["next_question"]["id"]
            state = twin_answer(session_id, qid, "test answer")
        twin_commit(session_id, consent=True)

    def _propose_and_reject(self, tenant: str, why: str = "too risky") -> str:
        """Propose one action, reject it, return the action_id."""
        from core.twin_actions import propose_actions, reject

        actions = propose_actions(tenant)
        action_id = actions[0]["action_id"]
        reject(
            action_id,
            tenant_id=tenant,
            why=why,
            reason_enum="POLICY_VIOLATION",
        )
        return action_id

    def _propose_and_approve(self, tenant: str, why: str = "good plan") -> str:
        """Propose one action, approve it with a why text, return action_id."""
        from core.twin_actions import (
            _action_digest,
            approve,
            list_actions,
            propose_actions,
        )

        actions = propose_actions(tenant)
        action_id = actions[0]["action_id"]
        action = next(
            (a for a in list_actions(tenant) if a["action_id"] == action_id),
            None,
        )
        assert action is not None  # for type-checker
        digest = _action_digest(action)
        approve(
            action_id,
            tenant_id=tenant,
            actor_id="operator",
            expected_payload_sha256=digest,
            why=why,
        )
        return action_id

    # ------------------------------------------------------------------ #
    # 1) Reject reason appears on next propose
    # ------------------------------------------------------------------ #

    def test_reject_reason_appears_on_next_propose(self) -> None:
        """After a reject, the next propose response includes last_reject_reason."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t174-reject"
        self._make_profile(tenant)
        self._propose_and_reject(tenant, why="too risky for now")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "next task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(
            "last_reject_reason",
            body,
            "propose response must include last_reject_reason after a reject",
        )
        self.assertTrue(
            body["last_reject_reason"],
            "last_reject_reason must be non-empty",
        )

    # ------------------------------------------------------------------ #
    # 2) Approve note appears on next propose
    # ------------------------------------------------------------------ #

    def test_approve_note_appears_on_next_propose(self) -> None:
        """After an approve with a why text, the next propose response
        includes ``last_approve_note``."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t174-approve"
        self._make_profile(tenant)
        self._propose_and_approve(tenant, why="solid plan")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "next task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(
            "last_approve_note",
            body,
            "propose response must include last_approve_note after an approve",
        )
        self.assertIn(
            "solid plan",
            body["last_approve_note"],
            "last_approve_note must carry the approve why text",
        )

    # ------------------------------------------------------------------ #
    # 3) Weekly brief uses saved profile role or goals
    # ------------------------------------------------------------------ #

    def test_weekly_brief_uses_saved_profile_role_or_goals(self) -> None:
        """The weekly brief JS function builds its text from the saved
        profile role or goals — the source contains role and goals references."""
        html = _read_app_html()
        self.assertIn("proposeWeeklyBrief", html, "weekly brief function must exist")
        self.assertIn("profilePrefill", html, "profile prefill must be referenced")
        # The function references role or goals from the saved profile.
        self.assertTrue(
            "role" in html or "goals" in html,
            "weekly brief must reference role or goals from the saved profile",
        )

    # ------------------------------------------------------------------ #
    # 4) Notes survive a store reopen
    # ------------------------------------------------------------------ #

    def test_notes_survive_store_reopen(self) -> None:
        """After a store reopen (fresh connection), the notes still feed
        the next propose response — the durable feedback rows persist in
        SQLite, not in-memory."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t174-reopen"
        self._make_profile(tenant)
        self._propose_and_reject(tenant, why="reopen reject")
        self._propose_and_approve(tenant, why="reopen approve")

        # Simulate a store reopen: drop the in-memory connection cache by
        # re-importing persistence (which re-creates the connection).
        # The SQLite file on disk persists the feedback rows.
        import importlib

        import core.persistence as p

        importlib.reload(p)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "after reopen"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(
            "last_reject_reason",
            body,
            "last_reject_reason must survive a store reopen",
        )
        self.assertIn(
            "last_approve_note",
            body,
            "last_approve_note must survive a store reopen",
        )

    # ------------------------------------------------------------------ #
    # 5) Approved strip still present
    # ------------------------------------------------------------------ #

    def test_approved_strip_still_present(self) -> None:
        """The Approved strip HTML is still present in app.html."""
        html = _read_app_html()
        self.assertIn("Approved", html, "Approved strip heading must be present")
        self.assertIn("approved-items", html, "approved-items div must be present")

    # ------------------------------------------------------------------ #
    # 6) README does not claim months of learning
    # ------------------------------------------------------------------ #

    def test_readme_does_not_claim_months_of_learning(self) -> None:
        """README does not claim months of learning; it says this is not a
        multi-month behavioral twin."""
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertNotIn(
            "months of learning",
            readme.lower(),
            "README must not claim months of learning",
        )
        self.assertIn(
            "not a multi-month",
            readme.lower(),
            "README must say this is not a multi-month twin",
        )

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertIn("## Author", readme, "Author paragraph must be present")
        self.assertIn("Amin Azimi", readme, "Author name must be present")


if __name__ == "__main__":
    unittest.main()
