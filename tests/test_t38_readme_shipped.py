"""T38 — README names shipped safety, errors, CI, and approve-outbox."""

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
    """README mentions EchoProvider (the default offline LLM)."""
    assert "EchoProvider" in _readme_text, (
        "README must mention EchoProvider (default offline LLM)."
    )


def test_readme_outbox_and_approve(_readme_text: str) -> None:
    """README mentions the local outbox and the approve gate."""
    assert "outbox" in _readme_text.lower(), (
        "README must mention 'outbox' (email-send writes local outbox only)."
    )
    assert "approve" in _readme_text.lower(), (
        "README must mention 'approve' (human approve gate)."
    )


def test_readme_ci(_readme_text: str) -> None:
    """README mentions ci.yml or GitHub Actions."""
    assert "ci.yml" in _readme_text or "GitHub Actions" in _readme_text, (
        "README must mention ci.yml or GitHub Actions."
    )


def test_readme_error_payload(_readme_text: str) -> None:
    """README mentions request_id, TWIN_NO_PROFILE, or api_errors."""
    assert (
        "request_id" in _readme_text
        or "TWIN_NO_PROFILE" in _readme_text
        or "api_errors" in _readme_text
    ), (
        "README must mention request_id, TWIN_NO_PROFILE, or api_errors."
    )


def test_no_live_network(_readme_text: str) -> None:
    """README does not claim live network calls or external integrations."""
    assert "requests.post" not in _readme_text
