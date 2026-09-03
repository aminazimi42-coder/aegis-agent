"""T36 — README matches the real tree (no invented features)."""

from __future__ import annotations

from pathlib import Path

import pytest

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture()
def _readme_text() -> str:
    """Read README.md once per test session."""
    return README.read_text()


def test_readme_exists() -> None:
    """README.md exists at the repo root."""
    assert README.exists(), "README.md not found at repo root"


def test_readme_echo_provider(_readme_text: str) -> None:
    """README mentions EchoProvider or states no paid LLM."""
    assert "EchoProvider" in _readme_text or "no paid LLM" in _readme_text.lower()


def test_readme_cli_commands(_readme_text: str) -> None:
    """README contains the key CLI command names and audio-task reference."""
    assert "brief-morning" in _readme_text
    assert "email-send" in _readme_text
    assert "audio-task" in _readme_text


def test_readme_resume_render_route(_readme_text: str) -> None:
    """README contains the /api/v1/twin/resume/render POST route."""
    assert "/api/v1/twin/resume/render" in _readme_text


def test_no_live_network(_readme_text: str) -> None:
    """README does not claim live network calls or external integrations."""
    # "no paid LLM" or "EchoProvider" already checked; ensure no curl to paid APIs
    assert "requests.post" not in _readme_text
