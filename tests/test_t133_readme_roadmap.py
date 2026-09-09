"""T133 — README Now vs Planned Destination tests.

Verifies that README.md has an Author paragraph (byte-stable), a Now
section and a Planned Destination section, and does not claim a
store-installer. No live network access — only local file reads.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = (REPO_ROOT / "README.md").read_text()


def test_author_paragraph_unchanged() -> None:
    """README Author paragraph is byte-stable (unchanged by T133)."""
    assert "## Author" in README, "README must have an Author section"
    assert "1.0.0-rc1" in README, "README Author paragraph must contain 1.0.0-rc1"
    assert "2026" in README, "README Author paragraph must contain 2026"
    assert "Amin Azimi" in README, "README Author paragraph must name Amin Azimi"
    assert "Azimi Innovation Lab" in README, (
        "README Author paragraph must mention Azimi Innovation Lab"
    )
    assert "End-to-End System Development" in README, (
        "README Author paragraph must mention End-to-End System Development"
    )


def test_readme_has_now_and_planned() -> None:
    """README has a Now section and a Planned Destination section."""
    low = README.lower()
    assert "## now" in low, "README must have a Now section"
    assert "## destination — planned" in low or "## destination - planned" in low, (
        "README must have a Destination section labeled Planned"
    )
    assert "planned" in low, "README Destination section must be labeled Planned"
    assert "echo" in low, "README Now section must mention Echo"


def test_readme_does_not_claim_store_installer() -> None:
    """README does not claim a store or marketplace installer is shipped."""
    low = README.lower()
    assert "app store installer" not in low, (
        "README must not claim an app-store installer is shipped"
    )
    assert "marketplace installer" not in low, (
        "README must not claim a marketplace installer is shipped"
    )
