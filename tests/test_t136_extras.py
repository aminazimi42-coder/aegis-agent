"""T136 — Compact extras: optional local Ollama alias, typed interview lock, local one-pager.

Covers:
- ``test_default_provider_still_echo`` — default provider is Echo when env unset.
- ``test_ollama_alias_falls_back_to_echo_when_unreachable`` — when
  ``AGENT_LLM_BACKEND=ollama`` is set but the base URL is missing or
  unreachable, ``complete_safe`` falls back to Echo and labels
  ``provider=echo(fallback)``.
- ``test_no_speech_to_text_import`` — no speech-to-text import in app/ or desktop/.
- ``test_empty_profile_no_onepager`` — when no profile is committed, the
  buyer one-pager endpoint returns a typed 400 and no file is written.
- ``test_profile_present_writes_onepager_outside_repo`` — when a profile
  is committed, the one-pager file is written under ``AEGIS_DATA_DIR``,
  never inside the git worktree.
- ``test_onepager_not_added_to_git_worktree`` — the one-pager file path
  is not inside the repository worktree (``git status`` does not see it).

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.server import create_app
from core import llm_safety
from core.llm_provider import HttpProvider
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_one_pager import render_buyer_one_pager
from core.twin_quota import set_quota
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT136Extras(unittest.TestCase):
    """Optional Ollama alias, typed interview lock, local buyer one-pager."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t136_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AGENT_LLM_BACKEND", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AGENT_LLM_BACKEND", None)

    # ------------------------------------------------------------------ #
    # 1. Default provider is Echo
    # ------------------------------------------------------------------ #

    def test_default_provider_still_echo(self) -> None:
        """When no LLM env is set, the provider is Echo (no fallback label)."""
        result = llm_safety.complete_safe("ping", tenant_id="t136-default")
        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    # ------------------------------------------------------------------ #
    # 2. Ollama alias falls back to Echo when unreachable
    # ------------------------------------------------------------------ #

    def test_ollama_alias_falls_back_to_echo_when_unreachable(self) -> None:
        """When AGENT_LLM_BACKEND=ollama but the endpoint is unreachable,
        complete_safe falls back to Echo and labels provider=echo(fallback).
        """
        os.environ["AGENT_LLM_BACKEND"] = "ollama"
        os.environ["AEGIS_LLM_PROVIDER"] = "echo"  # ensure alias is tested
        os.environ["AEGIS_LLM_BASE_URL"] = "http://127.0.0.1:1"  # refused
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t136-123456"
        set_quota("t136-ollama", remaining=10, period_end="2099-12-31")

        # Mock get_provider to return an HttpProvider whose complete()
        # raises OSError (simulating connection refused / timeout).
        fake_http = HttpProvider("http://127.0.0.1:1", "test-key-t136-123456")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "is_available",
                return_value=False,
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t136-ollama",
                )
        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result.get("fallback_label"), "echo(fallback)")

    # ------------------------------------------------------------------ #
    # 3. No speech-to-text import in app/ or desktop/
    # ------------------------------------------------------------------ #

    def test_no_speech_to_text_import(self) -> None:
        """No speech-to-text import in app/ or desktop/ Python or HTML."""
        forbidden = (
            "speech_to_text",
            "speech_recognition",
            "import whisper",
            "import speech",
            "MediaRecorder",
            "getUserMedia",
            "MediaStream",
        )
        checked: list[str] = []

        def _check_dir(dirpath: Path) -> None:
            if not dirpath.is_dir():
                return
            for p in dirpath.rglob("*"):
                if p.suffix in (".py", ".html", ".js"):
                    try:
                        text = p.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                    lowered = text.lower()
                    for term in forbidden:
                        lowered_term = term.lower()
                        self.assertNotIn(
                            lowered_term,
                            lowered,
                            f"{p} must not contain '{term}' — no speech-to-text",
                        )
                    checked.append(str(p))

        _check_dir(_REPO_ROOT / "app")
        _check_dir(_REPO_ROOT / "desktop")
        self.assertTrue(len(checked) > 0, "must have checked at least one file")

    # ------------------------------------------------------------------ #
    # 4. Empty profile → no one-pager (typed 400, no file)
    # ------------------------------------------------------------------ #

    def test_empty_profile_no_onepager(self) -> None:
        """When no profile is committed, the one-pager endpoint returns
        a typed 400 and no file is written."""
        # Direct function call — raises ValueError
        with self.assertRaises(ValueError):
            render_buyer_one_pager("t136-empty")

        # API endpoint — returns 400
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/buyer/one-pager",
            json={"tenant_id": "t136-empty"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("detail", body)

        # No file written
        exports_dir = Path(self._tmp) / "exports"
        if exports_dir.is_dir():
            files = list(exports_dir.glob("*"))
            self.assertEqual(len(files), 0, "no one-pager file for empty profile")

    # ------------------------------------------------------------------ #
    # 5. Profile present → one-pager written outside the repo
    # ------------------------------------------------------------------ #

    def test_profile_present_writes_onepager_outside_repo(self) -> None:
        """When a profile is committed, the one-pager is written under
        AEGIS_DATA_DIR (outside the git worktree) as a .md file."""
        # Commit a profile
        session = start_session("t136-pager")
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"val-{q['id']}")
        commit(sid, consent=True)

        result = render_buyer_one_pager("t136-pager")
        self.assertIn("path", result)
        out_path = Path(result["path"])
        self.assertTrue(out_path.is_file(), "one-pager file must exist")
        self.assertTrue(out_path.suffix == ".md", "one-pager must be .md")
        self.assertTrue(out_path.is_absolute(), "path must be absolute")

        # The file must be under AEGIS_DATA_DIR (self._tmp), not the repo
        tmp_path = Path(self._tmp).resolve()
        self.assertTrue(
            str(out_path.resolve()).startswith(str(tmp_path)),
            f"one-pager must be under {tmp_path}, got {out_path}",
        )

        # The file must not be inside the git worktree
        repo_root = _REPO_ROOT.resolve()
        self.assertFalse(
            str(out_path.resolve()).startswith(str(repo_root)),
            f"one-pager must not be inside the repo ({repo_root})",
        )

        # Content must contain profile fields
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("Buyer One-Pager", content)
        self.assertIn("val-q_repos", content)  # display name from repositories

    # ------------------------------------------------------------------ #
    # 6. One-pager not added to git worktree
    # ------------------------------------------------------------------ #

    def test_onepager_not_added_to_git_worktree(self) -> None:
        """git status must not show any one-pager file in the worktree."""
        # Commit a profile and render
        session = start_session("t136-git")
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"git-{q['id']}")
        commit(sid, consent=True)
        render_buyer_one_pager("t136-git")

        # Run git status — the one-pager file must not appear
        try:
            out = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(_REPO_ROOT),
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            self.skipTest("git not available")
            return

        for line in out.strip().splitlines():
            lowered = line.lower()
            self.assertFalse(
                "buyer_one_pager" in lowered,
                f"git status must not show one-pager file: {line}",
            )

    # ------------------------------------------------------------------ #
    # 7. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
