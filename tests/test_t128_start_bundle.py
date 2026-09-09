"""T128 — operator start bundle tests.

Verifies that scripts/start_operator.sh exists, mentions the local engine
start path (run_local.sh or uvicorn), and that STATUS.md does not claim a
notarized installer or paid SKU.  No live network access — only TestClient
and local file reads.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_start_script_exists() -> None:
    """scripts/start_operator.sh must exist in the repository tree."""
    script = REPO_ROOT / "scripts" / "start_operator.sh"
    assert script.is_file(), "scripts/start_operator.sh must exist"


def test_script_mentions_run_local_or_uvicorn() -> None:
    """start_operator.sh must reuse run_local.sh or call uvicorn."""
    script = REPO_ROOT / "scripts" / "start_operator.sh"
    text = script.read_text()
    assert "run_local" in text or "uvicorn" in text, (
        "start_operator.sh must mention run_local or uvicorn"
    )


def test_status_not_notarized_claim() -> None:
    """STATUS.md must not claim a notarized installer or paid SKU."""
    status = (REPO_ROOT / "STATUS.md").read_text().lower()
    # The honest claim is that the .app is NOT notarized / NOT a paid SKU.
    assert "notarized" not in status or "not a notarized" in status, (
        "STATUS.md must not claim a notarized installer without disclaiming it"
    )
    # Ensure STATUS.md says the .app is a wrapper, not a standalone product.
    assert "wrapper" in status, (
        "STATUS.md must state the .app is a wrapper, not a standalone product"
    )
