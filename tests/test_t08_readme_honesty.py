"""T08 — README honesty tests.

Verifies that README.md describes what the repo actually does and does
not make inflated claims about financial flows, autonomous settlement,
or live billing.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def readme_text() -> str:
    return Path("README.md").read_text()


class TestReadmeHonesty:
    """Assert README.md is honest about the shipped runtime."""

    def test_mentions_echo_provider(self, readme_text: str) -> None:
        """README must mention EchoProvider or Echo."""
        assert "Echo" in readme_text, (
            "README must mention EchoProvider (default offline LLM)."
        )

    def test_mentions_version_or_sqlite(self, readme_text: str) -> None:
        """README must mention 1.0.0-rc1 or SQLite."""
        assert "1.0.0-rc1" in readme_text or "SQLite" in readme_text, (
            "README must mention the version (1.0.0-rc1) or SQLite persistence."
        )

    def test_mentions_approve(self, readme_text: str) -> None:
        """README must mention the human approval gate."""
        assert "approve" in readme_text.lower(), (
            "README must mention the approve-before-execute gate."
        )

    def test_no_enterprise_candidate(self, readme_text: str) -> None:
        """README must not claim 'Enterprise Candidate' status."""
        assert "Enterprise Candidate" not in readme_text, (
            "README must not use the phrase 'Enterprise Candidate'."
        )

    def test_no_autonomous_settlement(self, readme_text: str) -> None:
        """README must not claim commitments settle autonomously."""
        lower = readme_text.lower()
        forbidden = [
            "settles financial flows",
            "automated settlement",
            "closes commitments autonomously",
        ]
        for phrase in forbidden:
            assert phrase not in lower, (
                f"README must not contain '{phrase}' — "
                "the platform does not settle or close commitments autonomously."
            )

    def test_no_monetization_as_live_billing(self, readme_text: str) -> None:
        """README must not present Monetization & Finance as live billing."""
        assert "Monetization & Finance" not in readme_text, (
            "README must not present 'Monetization & Finance' as a live billing feature."
        )

    def test_no_cinematic_acts_as_modules(self, readme_text: str) -> None:
        """README must not present cinematic acts as executable modules."""
        assert "Cinematic Acts" not in readme_text, (
            "README must not present 'Cinematic Acts' as executable runtime modules."
        )
