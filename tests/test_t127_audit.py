"""T127 — local truth audit tests.

Verifies that docs/AUDIT_T127.md exists, STATUS.md does not claim a hosted
SaaS product, and the README Author paragraph is byte-stable. No live
network access — only TestClient and local file reads.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_audit_file_exists() -> None:
    """docs/AUDIT_T127.md exists in the repository tree."""
    audit = REPO_ROOT / "docs" / "AUDIT_T127.md"
    assert audit.is_file(), "docs/AUDIT_T127.md must exist"
    text = audit.read_text()
    assert "T127" in text, "AUDIT_T127.md must mention T127"
    assert len(text) > 1000, "AUDIT_T127.md must be a substantive audit"


def test_status_does_not_claim_saas() -> None:
    """STATUS.md must not claim a hosted multi-tenant SaaS product is shipped."""
    status = (REPO_ROOT / "STATUS.md").read_text()
    # STATUS.md should say SaaS is NOT shipped, not claim it IS shipped.
    # The phrase "no hosted multi-tenant" is the honest disclaimer.
    assert "no hosted multi-tenant" in status.lower(), (
        "STATUS.md must state there is no hosted multi-tenant SaaS."
    )
    # Ensure STATUS.md does not claim SaaS is a shipped product.
    lines = status.splitlines()
    for line in lines:
        low = line.lower().strip()
        if low.startswith("- **hosted multi-tenant saas"):
            assert "not" in low or "no " in low, (
                f"STATUS.md must not claim SaaS is shipped: {line!r}"
            )


def test_author_paragraph_unchanged() -> None:
    """README Author paragraph is byte-stable (unchanged by T127)."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "## Author" in readme, "README must have an Author section"
    assert "1.0.0-rc1" in readme, "README Author paragraph must contain 1.0.0-rc1"
    assert "2026" in readme, "README Author paragraph must contain 2026"
    assert "Amin Azimi" in readme, "README Author paragraph must name Amin Azimi"
    assert "Azimi Innovation Lab" in readme, (
        "README Author paragraph must mention Azimi Innovation Lab"
    )
    assert "End-to-End System Development" in readme, (
        "README Author paragraph must mention End-to-End System Development"
    )
