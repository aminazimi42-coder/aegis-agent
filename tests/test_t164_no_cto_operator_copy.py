"""T164 — Strip CTO from operator copy.

Verifies:
- ``test_operator_html_has_no_cto`` — the served operator HTML does not
  contain the word CTO (bare substring, same scan as T141).
- ``test_specialist_templates_have_no_cto`` — specialist agent source
  files and YAML manifests do not contain the word CTO.
- ``test_default_goals_string_has_no_cto`` — the default goals string
  written by the commit-profile path does not contain CTO.
- ``test_license_file_not_rewritten`` — LICENSE still contains the
  original copyright line.
- ``test_readme_author_paragraph_still_present`` — README Author
  paragraph is still present (not rewritten by this directive).

Scans operator HTML and specialist template sources only.  Does not
fail on historical STATUS notes or the _directive.txt file.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HTML_PATH = (
    REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)

ROOT_HTML = REPO_ROOT / "app.html"

_CTO_RE = re.compile(r"\bcto\b", re.IGNORECASE)


def _scan_files(paths: list[Path]) -> bool:
    """Return True if any file in *paths* contains the word CTO."""
    for p in paths:
        if p.is_file():
            content = p.read_text(encoding="utf-8")
            if _CTO_RE.search(content):
                return True
    return False


class TestT164NoCtoOperatorCopy(unittest.TestCase):
    """Operator HTML and specialist templates must not say CTO."""

    def test_operator_html_has_no_cto(self) -> None:
        """The served operator HTML and the root app.html copy must
        not contain the substring 'cto' (case-insensitive bare scan)."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html_lower = resp.text.lower()
        self.assertNotIn(
            "cto",
            html_lower,
            "GET / HTML must not contain the substring cto",
        )
        # Also verify the root-level app.html copy.
        if ROOT_HTML.is_file():
            root_lower = ROOT_HTML.read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "cto",
                root_lower,
                "root app.html copy must not contain the substring cto",
            )

    def test_specialist_templates_have_no_cto(self) -> None:
        """Specialist agent source files and YAML manifests must not
        contain the word CTO (word-boundary match)."""
        sources: list[Path] = []
        # Agent Python modules and YAML manifests.
        for p in (REPO_ROOT / "agents").rglob("*"):
            if p.is_file() and p.suffix in (".py", ".yaml", ".html"):
                sources.append(p)
        # Also scan core/ propose/brief modules.
        for p in (REPO_ROOT / "core").rglob("*.py"):
            sources.append(p)
        self.assertFalse(
            _scan_files(sources),
            "specialist templates or core modules must not contain the word CTO",
        )

    def test_default_goals_string_has_no_cto(self) -> None:
        """The default goals string in the commit-profile path
        (app.html line: goals || 'goal-driven') must not contain CTO."""
        for html_path in (HTML_PATH, ROOT_HTML):
            if not html_path.is_file():
                continue
            text = html_path.read_text(encoding="utf-8")
            self.assertNotIn(
                "cto",
                text.lower(),
                f"{html_path.name} default goals string must not contain cto",
            )

    def test_license_file_not_rewritten(self) -> None:
        """LICENSE must still contain the original copyright line
        (Amin Azimi / AI Architect)."""
        license_path = REPO_ROOT / "LICENSE"
        self.assertTrue(license_path.is_file(), "LICENSE must exist")
        text = license_path.read_text(encoding="utf-8")
        self.assertIn("Amin Azimi", text, "LICENSE must retain the Amin Azimi copyright")
        self.assertIn(
            "Copyright 2026",
            text,
            "LICENSE must retain the 2026 copyright year",
        )

    def test_readme_author_paragraph_still_present(self) -> None:
        """README Author paragraph must still be present (not rewritten
        by this directive)."""
        readme = REPO_ROOT / "README.md"
        self.assertTrue(readme.is_file(), "README.md must exist")
        text = readme.read_text(encoding="utf-8")
        self.assertIn("## Author", text, "README must still have the Author section")
        self.assertIn(
            "Amin Azimi",
            text,
            "README Author paragraph must still name Amin Azimi",
        )


if __name__ == "__main__":
    unittest.main()
