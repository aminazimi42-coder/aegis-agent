"""T05 — Local git observer tests.

Covers:
- observe_repo without a consented profile raises ValueError.
- After a T03-style interview+commit, observing a tiny temp git repo
  ingests >= 1 commit, weekly_digest event_count >= 1, and the profile
  ``repositories`` layer mentions the temp repo name.
- A second observe on the same repo ingests == 0 (dedup by sha).
- FastAPI test client: POST /api/v1/twin/observe/git returns 200.
- All isolated with AEGIS_DATA_DIR temp dir; no live network / GitHub token.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from app.server import create_app
from core.twin_evolution import weekly_digest
from core.twin_git_observer import observe_repo
from core.twin_interview import QUESTIONS, answer, commit, get_latest_profile, start_session
from fastapi.testclient import TestClient


def _make_temp_git_repo(path: str) -> None:
    """Initialise a throwaway git repo at *path* with two commits."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(
        ["git", "-C", path, "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.name", "Test User"], check=True
    )
    (open(os.path.join(path, "README.md"), "w").close())
    subprocess.run(["git", "-C", path, "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", path, "commit", "-q", "-m", "first commit"], check=True
    )
    with open(os.path.join(path, "file2.txt"), "w"):
        pass
    subprocess.run(["git", "-C", path, "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", path, "commit", "-q", "-m", "second commit"], check=True
    )


class TestT05TwinGitObserver(unittest.TestCase):
    """Local git observer feeds twin events without network."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> None:
        """Run a complete T03 interview+commit so a profile exists."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_observe_without_profile_raises_value_error(self) -> None:
        repo_dir = tempfile.mkdtemp()
        _make_temp_git_repo(repo_dir)
        with self.assertRaises(ValueError):
            observe_repo("no_profile_t", repo_dir)

    def test_observe_ingests_and_updates_profile_repos(self) -> None:
        self._full_interview("t5a")
        repo_dir = tempfile.mkdtemp()
        _make_temp_git_repo(repo_dir)
        repo_name = os.path.basename(os.path.normpath(repo_dir))

        result = observe_repo("t5a", repo_dir, max_commits=20)
        self.assertGreaterEqual(result["ingested"], 1)
        self.assertEqual(result["tenant_id"], "t5a")
        self.assertEqual(result["repo"], repo_name)

        # weekly_digest should see at least one event.
        digest = weekly_digest("t5a")
        self.assertGreaterEqual(digest["event_count"], 1)

        # Profile repositories should mention the temp repo name.
        profile = get_latest_profile("t5a")
        assert profile is not None
        self.assertIn(repo_name, profile["repositories"])

    def test_second_observe_dedups_to_zero(self) -> None:
        self._full_interview("t5b")
        repo_dir = tempfile.mkdtemp()
        _make_temp_git_repo(repo_dir)

        first = observe_repo("t5b", repo_dir, max_commits=20)
        self.assertGreaterEqual(first["ingested"], 1)

        second = observe_repo("t5b", repo_dir, max_commits=20)
        self.assertEqual(second["ingested"], 0)

    def test_fastapi_observe_git_200(self) -> None:
        self._full_interview("t5c")
        repo_dir = tempfile.mkdtemp()
        _make_temp_git_repo(repo_dir)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/git",
            json={
                "tenant_id": "t5c",
                "repo_path": repo_dir,
                "max_commits": 20,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["ingested"], 1)
        self.assertEqual(body["tenant_id"], "t5c")

    def test_fastapi_observe_git_without_profile_400(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/git",
            json={
                "tenant_id": "no_profile_t",
                "repo_path": tempfile.mkdtemp(),
                "max_commits": 5,
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
