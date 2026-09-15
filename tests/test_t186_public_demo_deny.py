"""T186 — public demo denies raw PAT ingest; local loop unchanged.

Tests:
- demo flag on  -> observe/github with a fake PAT returns 403 and the
  token string is not written to disk.
- demo flag off -> existing local path is still callable in-process
  (no live GitHub).
- health is still 200 in demo mode (TestClient).
- README does not contain 'notarized' as a shipped claim.
- No live network; no uvicorn; no hit to aegis-agent-haka.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT186PublicDemoDeny(unittest.TestCase):
    """Public Render demo must not accept a raw GitHub PAT."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_GITHUB_TOKEN", None)
        os.environ.pop("AEGIS_PUBLIC_DEMO", None)
        os.environ.pop("RENDER", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_GITHUB_TOKEN", None)
        os.environ.pop("AEGIS_PUBLIC_DEMO", None)
        os.environ.pop("RENDER", None)

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

    def _walk_files(self) -> str:
        """Return concatenated file contents under the tmp data dir."""
        parts: list[str] = []
        root = Path(self._tmp)
        for p in root.rglob("*"):
            if p.is_file():
                parts.append(p.read_text(errors="replace"))
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_demo_flag_on_observes_github_403_and_no_token_on_disk(
        self,
    ) -> None:
        """demo flag on -> observe/github with a fake PAT is 403."""
        self._full_interview("t186a")
        os.environ["AEGIS_GITHUB_TOKEN"] = "ghp_fake_t186_not_real_token"
        os.environ["AEGIS_PUBLIC_DEMO"] = "1"

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/github",
            json={
                "tenant_id": "t186a",
                "repo": "owner/repo",
                "max_commits": 5,
            },
        )
        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body.get("code"), "TWIN_DEMO_INGEST_DENIED")
        # The fake PAT must not be written anywhere on disk.
        self.assertNotIn("ghp_fake_t186_not_real_token", self._walk_files())

    def test_demo_flag_off_local_path_still_callable(self) -> None:
        """demo flag off -> existing local path still callable in-process."""
        self._full_interview("t186b")
        # No AEGIS_GITHUB_TOKEN set; local path should still be callable
        # (returns a 400 ValueError response, not a 403 demo deny).
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/github",
            json={
                "tenant_id": "t186b",
                "repo": "owner/repo",
                "max_commits": 5,
            },
        )
        # Local mode: no demo deny -> existing behaviour (400 missing token).
        self.assertNotEqual(resp.status_code, 403)

    def test_render_env_triggers_demo_deny(self) -> None:
        """RENDER env var set -> demo deny (no AEGIS_PUBLIC_DEMO needed)."""
        self._full_interview("t186c")
        os.environ["AEGIS_GITHUB_TOKEN"] = "ghp_fake_render_t186"
        os.environ["RENDER"] = "true"

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/observe/github",
            json={
                "tenant_id": "t186c",
                "repo": "owner/repo",
                "max_commits": 5,
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("code"), "TWIN_DEMO_INGEST_DENIED")

    def test_health_still_200_in_demo_mode(self) -> None:
        """GET /health stays up in demo mode."""
        os.environ["AEGIS_PUBLIC_DEMO"] = "true"
        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_readme_does_not_claim_notarized(self) -> None:
        """README must not contain 'notarized' as a shipped claim."""
        repo_root = Path(__file__).resolve().parent.parent
        readme = (repo_root / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("notarized", readme.lower())


if __name__ == "__main__":
    unittest.main()
