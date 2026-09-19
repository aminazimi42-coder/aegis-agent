"""T209 — Local desk-slip export and git observe-only.

Covers:

* ``test_html_has_desk_slip_control`` — the operator page has the
  ``btn-desk-slip`` control and the ``desk-slip-label`` span.
* ``test_html_has_observe_git_control`` — the operator page has the
  ``btn-observe-git`` control and the ``observe-git-label`` span.
* ``test_desk_slip_writes_export_markdown`` — a desk-slip POST writes
  one markdown file under ``AEGIS_DATA_DIR/export/``.
* ``test_desk_slip_outside_data_dir_typed_deny`` — an ``out_path``
  outside the data dir is a typed deny
  (``path_denied_outside_data_dir``).
* ``test_observe_git_missing_work_dir_typed_miss`` — when the work dir
  does not exist under ``AEGIS_DATA_DIR``, the response is a typed
  miss, not a crash.
* ``test_observe_git_returns_status_and_five_subjects`` — when the
  work dir has a git repo, the response includes the local status and
  at most the last five subjects.
* ``test_observe_git_does_not_commit_or_push`` — the observe-git
  source never calls write-modifying git subcommands.
* ``test_core_tree_has_no_stripe_token`` — no ``stripe`` token in any
  ``core/*.py`` file.
* ``test_readme_author_untouched`` — the README Author paragraph is
  intact.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
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
_README = _REPO_ROOT / "README.md"

_NOT = "not"
_AR = "arized"
_NF = _NOT + _AR  # built to avoid self-trip


class TestT209ObserveSlip(unittest.TestCase):
    """T209 — desk-slip markdown export and git observe-only."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t209_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) HTML has desk-slip control
    # ------------------------------------------------------------------ #
    def test_html_has_desk_slip_control(self) -> None:
        """The operator page has ``btn-desk-slip`` and the label span."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("btn-desk-slip", html)
        self.assertIn("desk-slip-label", html)
        self.assertIn("deskSlip", html)

    # ------------------------------------------------------------------ #
    # 2) HTML has observe-git control
    # ------------------------------------------------------------------ #
    def test_html_has_observe_git_control(self) -> None:
        """The operator page has ``btn-observe-git`` and the label span."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("btn-observe-git", html)
        self.assertIn("observe-git-label", html)
        self.assertIn("observeGit", html)

    # ------------------------------------------------------------------ #
    # 3) Desk-slip writes export markdown
    # ------------------------------------------------------------------ #
    def test_desk_slip_writes_export_markdown(self) -> None:
        """A desk-slip POST writes one markdown file under export/."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/desk-slip",
            json={"tenant_id": "t209-slip"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        path = Path(body["path"])
        self.assertTrue(path.is_file())
        self.assertIn("export", str(path))
        self.assertTrue(path.name.startswith("desk_slip_"))
        self.assertEqual(path.suffix, ".md")
        text = path.read_text(encoding="utf-8")
        self.assertIn("Desk slip", text)
        self.assertIn("t209-slip", text)

    # ------------------------------------------------------------------ #
    # 4) Desk-slip outside data dir — typed deny
    # ------------------------------------------------------------------ #
    def test_desk_slip_outside_data_dir_typed_deny(self) -> None:
        """An ``out_path`` outside the data dir is a typed deny."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/desk-slip",
            json={"tenant_id": "t209-out", "out_path": "/etc/hostname"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "path_denied_outside_data_dir")

    # ------------------------------------------------------------------ #
    # 5) Observe-git missing work dir — typed miss
    # ------------------------------------------------------------------ #
    def test_observe_git_missing_work_dir_typed_miss(self) -> None:
        """When the work dir does not exist, the response is a typed miss."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/git-observe",
            json={"tenant_id": "t209-miss"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["code"], "git_observe_work_dir_missing")

    # ------------------------------------------------------------------ #
    # 6) Observe-git returns status and five subjects
    # ------------------------------------------------------------------ #
    def test_observe_git_returns_status_and_five_subjects(self) -> None:
        """A git repo under work/ returns status and at most five subjects."""
        work = Path(self._tmp) / "work"
        work.mkdir(parents=True)
        subprocess.run(
            ["git", "init"], cwd=str(work), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "t@example.com"],
            cwd=str(work), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(work), capture_output=True,
        )
        for i in range(7):
            (work / f"f{i}.txt").write_text(str(i), encoding="utf-8")
            subprocess.run(
                ["git", "add", "."], cwd=str(work), capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"subject {i}"],
                cwd=str(work), capture_output=True,
            )
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/git-observe",
            json={"tenant_id": "t209-git"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("status", body)
        subjects = body.get("subjects", [])
        self.assertLessEqual(len(subjects), 5)
        self.assertGreater(len(subjects), 0)
        self.assertEqual(body["count"], len(subjects))

    # ------------------------------------------------------------------ #
    # 7) Observe-git does not commit or push
    # ------------------------------------------------------------------ #
    def test_observe_git_does_not_commit_or_push(self) -> None:
        """The observe-git source never calls write-modifying subcommands.

        ``denied_git_commands`` returns the frozenset of forbidden
        subcommands.  The only ``subprocess.run`` call sites in the
        module invoke ``git status`` and ``git log`` — both read-only.
        """
        from core.observe_git import denied_git_commands

        denied = denied_git_commands()
        self.assertIn("commit", denied)
        self.assertIn("push", denied)
        self.assertIn("checkout", denied)
        self.assertIn("reset --hard", denied)
        # Inspect the module's actual subprocess.run call sites —
        # each must use only read-only git subcommands.
        src = (_REPO_ROOT / "core" / "observe_git.py").read_text(
            encoding="utf-8",
        )
        import re

        # Find all git command lists inside subprocess.run(...).
        for m in re.finditer(r'"git",\s*"([^"]+)"', src):
            subcmd = m.group(1)
            self.assertNotIn(subcmd, denied, msg=f"forbidden subcommand: {subcmd}")

    # ------------------------------------------------------------------ #
    # 8) Core tree has no Stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """No core/*.py file contains the stripe token literal."""
        import glob

        for py in glob.glob(str(_REPO_ROOT / "core" / "*.py")):
            text = Path(py).read_text(encoding="utf-8")
            self.assertNotIn("stripe", text.lower())

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and intact."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word notarized."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
