"""T194 — Live local LLM path only.

Covers:

* ``test_default_engine_is_echo`` — with no env, ``engine_label`` is Echo.
* ``test_missing_url_with_ollama_alias_is_echo`` — ``AGENT_LLM_BACKEND=ollama``
  but no base URL stays Echo.
* ``test_set_url_label_is_http_or_ollama_alias`` — when the URL is set and
  the provider is reachable, the label is ``HTTP (Ollama alias)``.
* ``test_unreachable_url_is_echo_fallback`` — when the URL is set but the
  provider is unreachable, the label is ``Echo (fallback)``.
* ``test_operator_html_shows_engine_line`` — the operator HTML contains an
  ``engine-line`` span and the ``Engine:`` prefix.
* ``test_no_live_llm_key_in_repo_text`` — no live key shape is committed
  under ``app/``, ``tests/``, ``scripts/``, or ``docs/``.
* ``test_readme_author_untouched`` — the README Author paragraph is present.
* ``test_readme_does_not_contain_notarized`` — the word *notarized* is not
  in the README.
* ``test_readme_does_not_claim_bundled_ollama`` — the README does not claim
  Ollama is bundled.

Mock HTTP only.  Use ``tmp_path`` as ``AEGIS_DATA_DIR``.  Do not write live
``$HOME/.aegis``.  Do not start uvicorn.  No ``xfail``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT194(unittest.TestCase):
    """T194 — honest operator engine line for the local LLM path."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t194_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clear all LLM env vars so each test starts clean.
        for key in (
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_BASE_URL",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_BUDGET_EXHAUSTED",
            "AEGIS_OFFLINE",
            "AGENT_LLM_BACKEND",
        ):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        for key in (
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_BASE_URL",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_BUDGET_EXHAUSTED",
            "AEGIS_OFFLINE",
            "AGENT_LLM_BACKEND",
        ):
            os.environ.pop(key, None)

    # ------------------------------------------------------------------ #
    # 1) Default engine is Echo
    # ------------------------------------------------------------------ #

    def test_default_engine_is_echo(self) -> None:
        """With no LLM env set, engine_label returns 'Echo'."""
        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo")

    # ------------------------------------------------------------------ #
    # 2) Missing URL with ollama alias is Echo
    # ------------------------------------------------------------------ #

    def test_missing_url_with_ollama_alias_is_echo(self) -> None:
        """AGENT_LLM_BACKEND=ollama but no base URL stays Echo."""
        os.environ["AGENT_LLM_BACKEND"] = "ollama"
        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo")

    # ------------------------------------------------------------------ #
    # 3) Set URL label is HTTP (Ollama alias)
    # ------------------------------------------------------------------ #

    def test_set_url_label_is_http_or_ollama_alias(self) -> None:
        """When the URL is set and the provider is reachable, the label
        is 'HTTP (Ollama alias)'."""
        os.environ["AGENT_LLM_BACKEND"] = "ollama"
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:11434"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t194-123456"

        from core.llm_provider import HttpProvider, engine_label

        fake_http = HttpProvider(
            "http://localhost:11434", "test-key-t194-123456",
        )
        with mock.patch("core.llm_provider.get_provider", return_value=fake_http):
            with mock.patch.object(fake_http, "is_available", return_value=True):
                label = engine_label()
        self.assertEqual(label, "HTTP (Ollama alias)")

    # ------------------------------------------------------------------ #
    # 4) Unreachable URL is Echo (fallback)
    # ------------------------------------------------------------------ #

    def test_unreachable_url_is_echo_fallback(self) -> None:
        """When the URL is set but the provider is unreachable, the label
        is 'Echo (fallback)'."""
        os.environ["AGENT_LLM_BACKEND"] = "ollama"
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://127.0.0.1:1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t194-123456"

        from core.llm_provider import HttpProvider, engine_label

        fake_http = HttpProvider("http://127.0.0.1:1", "test-key-t194-123456")
        with mock.patch("core.llm_provider.get_provider", return_value=fake_http):
            with mock.patch.object(fake_http, "is_available", return_value=False):
                label = engine_label()
        self.assertEqual(label, "Echo (fallback)")

    # ------------------------------------------------------------------ #
    # 5) Operator HTML shows engine line
    # ------------------------------------------------------------------ #

    def test_operator_html_shows_engine_line(self) -> None:
        """The operator HTML contains an engine-line span and Engine: prefix."""
        html = Path("app.html").read_text("utf-8")
        self.assertIn("engine-line", html)
        self.assertIn("Engine:", html)
        # Desktop bundle matches repo.
        desk = Path(
            "desktop/macos/Aegis.app/Contents/Resources/app.html"
        ).read_text("utf-8")
        self.assertEqual(html, desk)

    # ------------------------------------------------------------------ #
    # 6) No live LLM key in repo text
    # ------------------------------------------------------------------ #

    def test_no_live_llm_key_in_repo_text(self) -> None:
        """No live key shape is committed under app/, tests/, scripts/,
        or docs/."""

        # Live-key shapes that must never appear in repo source files.
        # These match *real* key shapes: long enough to be a live secret,
        # not the short placeholder strings used in test fixtures.
        patterns: list[str] = [
            # OpenAI-style live key: sk- followed by 32+ alphanumerics.
            r"sk-[a-zA-Z0-9]{32,}",
            # Stripe-style live key: sk_live_ followed by 24+ alphanumerics.
            r"sk_live_[a-zA-Z0-9]{24,}",
            # Anthropic key assignment: anthropic-key = "long value"
            r'anthropic[-_]key\s*=\s*["\'][a-zA-Z0-9_-]{20,}["\']',
        ]

        import re

        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

        # Dirs to scan for live keys.
        scan_dirs = [
            _REPO_ROOT / "app",
            _REPO_ROOT / "tests",
            _REPO_ROOT / "scripts",
            _REPO_ROOT / "docs",
        ]

        # File extensions to scan.
        scan_exts = {
            ".py", ".html", ".js", ".sh", ".md",
            ".json", ".yaml", ".yml", ".txt",
        }

        # Exclude this test file itself.
        exclude = Path(__file__).resolve()

        checked = 0
        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for p in scan_dir.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix not in scan_exts:
                    continue
                if p.resolve() == exclude:
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for regex in compiled:
                    for m in regex.finditer(text):
                        matched = m.group()
                        # Skip if the match is inside a comment line.
                        line_start = text.rfind("\n", 0, m.start()) + 1
                        line = text[line_start:text.find("\n", m.start())]
                        stripped = line.lstrip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        self.fail(
                            f"Live key shape {matched!r} found in {p}:\n"
                            f"  {line.strip()}",
                        )
                checked += 1
        self.assertGreater(checked, 0, "must have scanned at least one file")

    # ------------------------------------------------------------------ #
    # 7) README author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and unchanged."""
        text = Path("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 8) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The word *notarized* does not appear in the README."""
        text = Path("README.md").read_text("utf-8")
        lower = text.lower()
        self.assertNotIn("nota" + "rized", lower)

    # ------------------------------------------------------------------ #
    # 9) README does not claim bundled Ollama
    # ------------------------------------------------------------------ #

    def test_readme_does_not_claim_bundled_ollama(self) -> None:
        """The README does not claim Ollama is bundled."""
        text = Path("README.md").read_text("utf-8")
        lower = text.lower()
        self.assertNotIn("ollama is bundled", lower)
        self.assertNotIn("bundled ollama", lower)


if __name__ == "__main__":
    unittest.main()
