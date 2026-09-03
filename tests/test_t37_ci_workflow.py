"""T37 — GitHub Actions CI workflow on main."""

from __future__ import annotations

from pathlib import Path

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_exists() -> None:
    """ci.yml exists under .github/workflows/."""
    assert CI.is_file(), "ci.yml not found"


def test_ci_workflow_contains_ruff_and_pytest() -> None:
    """ci.yml runs ruff check and pytest."""
    text = CI.read_text()
    assert "ruff check" in text, "missing 'ruff check'"
    assert "pytest" in text, "missing 'pytest'"


def test_ci_workflow_python_version() -> None:
    """ci.yml targets Python 3.11."""
    text = CI.read_text()
    assert "3.11" in text, "missing python 3.11"


def test_ci_workflow_triggers_pull_request() -> None:
    """ci.yml triggers on pull_request to main."""
    text = CI.read_text()
    assert "pull_request" in text, "missing pull_request trigger"


def test_ci_no_live_network() -> None:
    """ci.yml does not reference live network beyond pip and GitHub."""
    text = CI.read_text()
    assert "requests.post" not in text
    assert "urllib.request" not in text
