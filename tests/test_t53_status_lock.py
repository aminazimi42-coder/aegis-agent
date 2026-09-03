"""T53 — lock honest shipped-capability status in STATUS.md.

No live network.  Tests assert that STATUS.md describes the real shipped
capabilities and that the codebase matches those claims.
"""

from __future__ import annotations

import os
from pathlib import Path

# Ensure no live network is attempted by the provider during this test run.
os.environ.setdefault("AEGIS_LLM_PROVIDER", "echo")

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = REPO_ROOT / "STATUS.md"


# --------------------------------------------------------------------------- #
# STATUS.md content lock
# --------------------------------------------------------------------------- #
def test_status_md_contains_echo_provider_and_not_shipped() -> None:
    """STATUS.md must mention EchoProvider and a Not shipped section."""
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "EchoProvider" in text, "STATUS.md must mention EchoProvider"
    assert "Not shipped" in text, "STATUS.md must contain a 'Not shipped' section"


def test_status_md_contains_optional_http_provider() -> None:
    """STATUS.md should document the optional HTTP provider."""
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert "Optional" in text or "optional" in text


# --------------------------------------------------------------------------- #
# Provider default lock
# --------------------------------------------------------------------------- #
def test_default_provider_is_echo_provider() -> None:
    """With default env, get_provider() must return an EchoProvider instance."""
    # Clear any override so get_provider() falls back to its default.
    saved = os.environ.pop("AEGIS_LLM_PROVIDER", None)
    try:
        from core.llm_provider import get_provider

        provider = get_provider()
        assert type(provider).__name__ == "EchoProvider"
    finally:
        if saved is not None:
            os.environ["AEGIS_LLM_PROVIDER"] = saved


# --------------------------------------------------------------------------- #
# No Stripe in core/
# --------------------------------------------------------------------------- #
def test_core_tree_has_no_stripe_references() -> None:
    """No file under core/ may contain the word 'stripe' (case-insensitive)."""
    core_dir = REPO_ROOT / "core"
    offenders: list[str] = []
    for path in core_dir.rglob("*"):
        if path.is_file() and path.suffix == ".py":
            content = path.read_text(encoding="utf-8", errors="replace")
            if "stripe" in content.lower():
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"Found 'stripe' references in core/: {offenders}"


# --------------------------------------------------------------------------- #
# Callable capability lock
# --------------------------------------------------------------------------- #
def test_execute_is_callable() -> None:
    from core.twin_actions import execute

    assert callable(execute)


def test_render_home_is_callable() -> None:
    from core.twin_home import render_home

    assert callable(render_home)


def test_schedule_is_callable() -> None:
    from core.twin_scheduler import schedule

    assert callable(schedule)


def test_send_approved_is_callable() -> None:
    from core.twin_email_send import send_approved

    assert callable(send_approved)
