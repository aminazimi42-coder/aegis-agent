"""T54 — author identity and Apache-2.0 license lock test."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_license_is_apache_with_brands() -> None:
    """LICENSE contains Apache and both brand names."""
    text = (REPO_ROOT / "LICENSE").read_text()
    assert "Apache" in text
    assert "Azimi Innovation Lab" in text
    assert "End-to-End System Development" in text


def test_readme_has_author_section_and_version() -> None:
    """README.md contains ## Author and 1.0.0-rc1 and 2026."""
    text = (REPO_ROOT / "README.md").read_text()
    assert "## Author" in text
    assert "1.0.0-rc1" in text
    assert "2026" in text


def test_readmd_does_not_say_proprietary() -> None:
    """README.md does not contain the old Proprietary badge text."""
    text = (REPO_ROOT / "README.md").read_text()
    assert "License-Proprietary" not in text
