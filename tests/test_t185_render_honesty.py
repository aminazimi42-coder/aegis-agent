"""T185 — Render honesty pack tests.

Verifies that README and STATUS match the live dashboard, that the
free-tier/cold-start sentence is gone, that LIMITATIONS.md and
THREAT_NOTES.md exist, and that the Author paragraph is untouched.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
STATUS = REPO / "STATUS.md"
LIMITATIONS = REPO / "docs" / "LIMITATIONS.md"
THREAT_NOTES = REPO / "docs" / "THREAT_NOTES.md"


class TestT185RenderHonesty(unittest.TestCase):
    """Lock the T185 render-honesty deliverables."""

    def setUp(self) -> None:
        self.readme = README.read_text()
        self.status = STATUS.read_text()

    def test_readme_contains_live_host(self) -> None:
        """README contains the live demo hostname."""
        self.assertIn("aegis-agent-haka.onrender.com", self.readme)

    def test_status_contains_live_host(self) -> None:
        """STATUS contains the live demo hostname."""
        self.assertIn("aegis-agent-haka.onrender.com", self.status)

    def test_readme_does_not_present_old_hostname_as_live(self) -> None:
        """README does not present aegis-agent-platform.onrender.com as the live URL."""
        self.assertNotIn("aegis-agent-platform.onrender.com", self.readme)

    def test_readme_does_not_claim_free_spin_down(self) -> None:
        """README does not claim the current Render service is the free spin-down plan."""
        lower = self.readme.lower()
        # The old sentence "On a free Render instance the service may
        # cold-start and lose in-memory state" must be gone.
        self.assertNotIn("free render instance", lower)
        self.assertNotIn("cold-start", lower)

    def test_readme_does_not_claim_notarized(self) -> None:
        """README does not contain the word notarized as a shipped claim."""
        self.assertNotIn("notarized", self.readme.lower())

    def test_limitations_doc_exists(self) -> None:
        """docs/LIMITATIONS.md exists and is non-empty."""
        self.assertTrue(LIMITATIONS.is_file())
        self.assertGreater(len(LIMITATIONS.read_text().strip()), 100)

    def test_threat_notes_doc_exists(self) -> None:
        """docs/THREAT_NOTES.md exists and is non-empty."""
        self.assertTrue(THREAT_NOTES.is_file())
        self.assertGreater(len(THREAT_NOTES.read_text().strip()), 100)

    def test_author_paragraph_untouched(self) -> None:
        """The Author paragraph in README is present and unchanged."""
        self.assertIn("Amin Azimi", self.readme)
        self.assertIn("Azimi Innovation Lab", self.readme)


if __name__ == "__main__":
    unittest.main()
