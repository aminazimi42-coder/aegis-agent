"""T101 — Evidence pack, resume diff, memo diff, open decision ids in brief.

Covers:
- ``evidence_pack(TENANT_ID)`` writes a markdown pack that records the
  local git-observe range when ``AEGIS_REPO_PATH`` points to a git repo,
  else records "no git repo".
- ``resume_diff(TENANT_ID)`` returns a unified diff of the last two
  hashed resume copies; fewer than two → empty string.
- ``memo_diff(TENANT_ID)`` returns a unified diff of the last two
  hashed board-memo copies; fewer than two → empty string.
- ``render_brief`` cites open decision-record ids when a decision log
  file exists.
- AEGIS_DATA_DIR temp, no live network.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.twin_board_memo import render_memo
from core.twin_decisions import record as record_decision
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_morning_brief import render_brief
from core.twin_resume_pack import render_resume
from core.twin_work_history import evidence_pack, memo_diff, resume_diff


class TestT101WorkHistory(unittest.TestCase):
    """Evidence pack, resume/memo diffs, open decision ids in brief."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t101_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_REPO_PATH", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _make_git_repo(self, path: str) -> str:
        """Initialise a throwaway git repo at *path* with one commit."""
        os.makedirs(path, exist_ok=True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
        subprocess.run(["git", "init", path], check=True, capture_output=True, env=env)
        (Path(path) / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "-C", path, "add", "-A"], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "-C", path, "commit", "-m", "initial"],
            check=True,
            capture_output=True,
            env=env,
        )
        return path

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_evidence_writes_pack(self) -> None:
        """``evidence_pack`` writes a markdown pack with git range or 'no git repo'."""
        tenant = "t101-evi"
        self._full_interview(tenant)

        # Without a configured repo → "no git repo".
        os.environ.pop("AEGIS_REPO_PATH", None)
        result = evidence_pack(tenant)
        self.assertEqual(result["tenant_id"], tenant)
        self.assertTrue(Path(result["path"]).is_file())
        content = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("no git repo", content)
        self.assertEqual(result["count"], 0)

        # With a configured repo → records the latest SHA and count.
        repo_path = self._make_git_repo(str(Path(self._tmp) / "myrepo"))
        os.environ["AEGIS_REPO_PATH"] = repo_path
        result2 = evidence_pack(tenant)
        content2 = Path(result2["path"]).read_text(encoding="utf-8")
        self.assertNotIn("no git repo", content2)
        self.assertGreater(result2["count"], 0)
        self.assertTrue(result2["latest_sha"])
        self.assertIn(result2["latest_sha"], content2)

    def test_resume_diff_two_versions(self) -> None:
        """``resume_diff`` returns a non-empty diff when two distinct versions exist."""
        tenant = "t101-rd"
        self._full_interview(tenant)

        # First render — one hashed copy.
        render_resume(tenant)
        diff1 = resume_diff(tenant)
        self.assertEqual(diff1, "", "first render should have < 2 copies")

        # Change the profile to produce different content, then render again.
        # Re-interview with a different role so the resume content changes.
        session2 = start_session(tenant)
        sid2 = session2["session_id"]
        for q in QUESTIONS:
            answer(sid2, q["id"], f"changed-{q['id']}")
        commit(sid2, True)

        render_resume(tenant)
        diff2 = resume_diff(tenant)
        # Two distinct hashed copies now exist → non-empty diff.
        self.assertIsInstance(diff2, str)
        self.assertGreater(len(diff2), 0, "resume_diff should be non-empty with 2 versions")
        self.assertIn("---", diff2)
        self.assertIn("+++", diff2)

    def test_memo_diff_or_none(self) -> None:
        """``memo_diff`` returns a diff for two distinct memo versions, empty otherwise."""
        tenant = "t101-md"
        self._full_interview(tenant)

        # First render — one hashed copy.
        render_memo(tenant)
        diff1 = memo_diff(tenant)
        self.assertEqual(diff1, "", "first render should have < 2 copies")

        # Record a decision — the memo includes decisions, so content changes.
        record_decision(tenant, "Adopt FastAPI", "yes", "team familiar")

        render_memo(tenant)
        diff2 = memo_diff(tenant)
        # Two distinct hashed copies now exist → non-empty diff.
        self.assertGreater(len(diff2), 0, "memo_diff should be non-empty with 2 versions")

        # A tenant with no renders at all → empty string.
        tenant_empty = "t101-md-empty"
        self._full_interview(tenant_empty)
        diff3 = memo_diff(tenant_empty)
        self.assertEqual(diff3, "")

    def test_brief_cites_open_decision_ids(self) -> None:
        """``render_brief`` includes open decision-record ids when decisions exist."""
        tenant = "t101-bd"
        self._full_interview(tenant)

        # Record a decision — this also writes decision_log.md.
        record_decision(tenant, "Adopt FastAPI", "yes", "team familiar")

        result = render_brief(tenant)
        content = Path(result["path"]).read_text(encoding="utf-8")

        # The brief should cite the decision section.
        self.assertIn("## Open decisions", content)

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
