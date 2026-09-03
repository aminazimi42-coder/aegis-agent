"""T10 — GitHub PAT read-only observer tests.

Covers:
- observe_github without a consented profile raises ValueError.
- observe_github with profile but no token raises ValueError.
- observe_github with profile + token and urlopen monkeypatched to return
  two fake commits: ingested >= 1.
- Second call with same fake payload: ingested == 0 (dedup by sha).
- FastAPI client returns 200 when token set and urlopen patched.
- No live network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from app.server import create_app
from core.twin_github_observer import observe_github
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient

_FAKE_COMMITS = [
    {
        "sha": "abc123def456",
        "commit": {"message": "feat: add new feature\n\nCo-authored-by: test"},
    },
    {
        "sha": "def789abc012",
        "commit": {"message": "fix: resolve bug"},
    },
]


class _FakeResponse:
    """Minimal context-manager mimicking urllib's HTTP response."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass


class TestT10TwinGithubObserver(unittest.TestCase):
    """GitHub PAT observer feeds twin events; tests mock urllib."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_GITHUB_TOKEN", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_GITHUB_TOKEN", None)

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

    def _patched_urlopen(self, commits: list[dict] | None = None):
        """Return a mock.patch context for urlopen returning fake commits."""
        body = json.dumps(commits or _FAKE_COMMITS).encode("utf-8")
        return mock.patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse(body),
        )

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_without_profile_raises_value_error(self) -> None:
        os.environ["AEGIS_GITHUB_TOKEN"] = "test-token-not-real"
        with self.assertRaises(ValueError):
            observe_github("no_profile_t", "owner/repo")

    def test_with_profile_no_token_raises_value_error(self) -> None:
        self._full_interview("t10a")
        with self.assertRaises(ValueError):
            observe_github("t10a", "owner/repo")

    def test_ingests_with_profile_and_token(self) -> None:
        self._full_interview("t10b")
        os.environ["AEGIS_GITHUB_TOKEN"] = "test-token-not-real"
        with self._patched_urlopen():
            result = observe_github("t10b", "owner/repo", max_commits=20)
        self.assertGreaterEqual(result["ingested"], 1)
        self.assertEqual(result["tenant_id"], "t10b")
        self.assertEqual(result["repo"], "owner/repo")

    def test_second_call_dedups_to_zero(self) -> None:
        self._full_interview("t10c")
        os.environ["AEGIS_GITHUB_TOKEN"] = "test-token-not-real"
        with self._patched_urlopen():
            first = observe_github("t10c", "owner/repo", max_commits=20)
        self.assertGreaterEqual(first["ingested"], 1)

        with self._patched_urlopen():
            second = observe_github("t10c", "owner/repo", max_commits=20)
        self.assertEqual(second["ingested"], 0)

    def test_fastapi_observe_github_200(self) -> None:
        self._full_interview("t10d")
        os.environ["AEGIS_GITHUB_TOKEN"] = "test-token-not-real"
        app = create_app()
        client = TestClient(app)
        with self._patched_urlopen():
            resp = client.post(
                "/api/v1/twin/observe/github",
                json={
                    "tenant_id": "t10d",
                    "repo": "owner/repo",
                    "max_commits": 20,
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["ingested"], 1)

    def test_fastapi_observe_github_no_token_400(self) -> None:
        self._full_interview("t10e")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/github",
            json={
                "tenant_id": "t10e",
                "repo": "owner/repo",
                "max_commits": 5,
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
