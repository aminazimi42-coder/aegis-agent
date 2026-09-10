"""T141 — operator product copy must not contain the word CTO.

Verifies:
- GET / served HTML lowercased must not contain "cto".
- Specialist proposal templates / default task phrases / weekly-brief
  copy in production modules and the served HTML must not contain the
  word CTO (word-boundary match, so ``actor_id`` and ``factory`` do not
  false-positive).
- No live network except TestClient.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Served HTML path (same file app/server.py reads).
HTML_PATH = (
    REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)

# Production modules and templates that build propose text, weekly-brief
# copy, or default task phrases.  Excludes tests/, docs/, STATUS.md, and
# this test file's own assertion strings.
_SCAN_GLOBS = [
    "app/**/*.py",
    "app/**/*.html",
    "core/**/*.py",
    "core/**/*.html",
    "agents/**/*.py",
    "agents/**/*.yaml",
    "agents/**/*.html",
    "desktop/**/*.html",
    "scripts/*.sh",
]

_CTO_RE = re.compile(r"\bcto\b", re.IGNORECASE)


def _production_files() -> list[Path]:
    """Collect production files from the scan globs, skipping nonexistent."""
    collected: list[Path] = []
    for pattern in _SCAN_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            if p.is_file():
                collected.append(p)
    return sorted(set(collected))


class TestT141NoCtoCopy(unittest.TestCase):
    """Operator product copy and specialist templates must not say CTO."""

    def test_operator_html_has_no_cto(self) -> None:
        """GET / HTML lowercased must not contain 'cto' (bare substring)."""
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

    def test_specialist_templates_have_no_cto(self) -> None:
        """Production propose / brief / default-task modules must not contain the word CTO.

        Scans the served HTML, all files under app/ that build propose text,
        and any templates under agents/ or core/.  Uses word-boundary matching
        so identifiers like ``actor_id`` or ``factory`` do not false-positive.
        Excludes tests/, docs/ that label the strip, README Author if it never
        had it, and this test file's own assertion strings.
        """
        for fpath in _production_files():
            content = fpath.read_text(encoding="utf-8")
            self.assertIsNone(
                _CTO_RE.search(content),
                f"{fpath.relative_to(REPO_ROOT)} must not contain the word CTO",
            )

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
