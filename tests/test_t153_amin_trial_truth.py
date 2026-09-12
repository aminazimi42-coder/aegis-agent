"""T153 — Record the proven amin installer-path laptop trial.

Tests that README.md and STATUS.md honestly state the observed laptop facts
without claiming notarization, App Store, one-click install, or that
Aegis Operator.app was opened on amin.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
STATUS = REPO_ROOT / "STATUS.md"


def test_readme_records_amin_install_command_trial() -> None:
    """README Now records the amin Install.command trial on 2026-09-13."""
    text = README.read_text()
    assert "2026-09-13" in text, "README must mention the 2026-09-13 trial date"
    assert "Install.command" in text, "README must mention Install.command"
    assert "amin" in text.lower(), "README must mention the amin account"
    assert "start_operator.sh" in text, "README must mention start_operator.sh"
    assert "127.0.0.1:8741" in text, "README must mention the bound port"
    assert "twin-1ca1a06ea177" in text, "README must mention the session id"
    assert "act-7142b446680f" in text, "README must mention Alina action id"
    assert "act-c1c6e615c0bc" in text, "README must mention Bita action id"
    assert "5007b9cd47d9" in text, "README must mention the export sha256"
    assert "Echo-limited" in text or "missing_file" in text, (
        "README must mention Echo-limited entitlement"
    )


def test_readme_says_venv_still_required() -> None:
    """README honestly states that a Terminal venv is still required."""
    text = README.read_text().lower()
    assert "venv" in text, "README must mention venv is still required"


def test_readme_does_not_claim_app_opened_or_notarized() -> None:
    """README does not claim the app was opened or that it is notarized."""
    text = README.read_text()
    lower = text.lower()
    assert "app store" not in lower, "README must not mention App Store"
    # 'notarized' may appear only in negation ("not notarized") — check for
    # any standalone claim of notarization.
    assert "notarized" not in lower or "not notarized" in lower, (
        "README must not claim notarization except in honest negation"
    )
    # Must state that Aegis Operator.app was not opened.
    assert "was not opened" in lower, (
        "README must state Aegis Operator.app was not opened"
    )


def test_status_no_longer_says_trial_not_yet_recorded() -> None:
    """STATUS.md no longer says the trial was not yet recorded."""
    text = STATUS.read_text().lower()
    assert "not yet recorded" not in text, (
        "STATUS must not still say trial not yet recorded"
    )


def test_status_says_amin_2026_09_13() -> None:
    """STATUS.md records the amin 2026-09-13 installer-path trial."""
    text = STATUS.read_text()
    assert "amin" in text.lower(), "STATUS must mention amin"
    assert "2026-09-13" in text, "STATUS must mention 2026-09-13"
    assert "Install.command" in text, "STATUS must mention Install.command"
    assert "start_operator.sh" in text, "STATUS must mention start_operator.sh"
    assert "signed export" in text.lower() or "signed-export" in text.lower(), (
        "STATUS must mention the signed export"
    )
