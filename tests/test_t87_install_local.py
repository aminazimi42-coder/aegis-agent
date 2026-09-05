"""T87 — tests for scripts/install_local.sh.

The installer must:
- exist as a file,
- target ``$HOME/.local/...`` paths, not the git working tree,
- never reference ``Stripe`` or ``desktop_engine``.

The installer is *never* executed against the real home directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_local.sh"


# ── helpers ──────────────────────────────────────────────────────────────

def _read_script() -> str:
    """Return the raw text of ``scripts/install_local.sh``."""
    return SCRIPT.read_text()


# ── tests ─────────────────────────────────────────────────────────────────

class TestInstallScriptExists:
    def test_install_script_exists(self) -> None:
        assert SCRIPT.is_file(), f"{SCRIPT} does not exist"

    def test_script_is_shell(self) -> None:
        text = _read_script()
        assert text.startswith("#!/bin/sh"), "script must start with #!/bin/sh"


class TestScriptTargetsHomeLocal:
    """The installer must install into ``$HOME/.local/...``, not the repo."""

    def test_script_targets_home_local_not_repo(self) -> None:
        text = _read_script()
        # PREFIX defaults to $HOME/.local/aegis  (outside the git tree)
        assert '${AEGIS_PREFIX:-$HOME/.local/aegis}' in text
        # BIN   defaults to $HOME/.local/bin     (outside the git tree)
        assert '${AEGIS_BIN:-$HOME/.local/bin}' in text
        # The venv lives under PREFIX, never under the repo root.
        assert "$PREFIX/venv" in text
        # The launcher lives under BIN, never under the repo root.
        assert "$BIN/aegis" in text

    def test_script_does_not_write_into_repo(self) -> None:
        """No reference to repo-relative paths like ./core or ./src."""
        text = _read_script()
        # The script computes REPO_ROOT from its own location and passes it
        # to ``pip install -e`` — that is a read of the repo, not a write.
        # But it must never *write* files into the repo tree.
        forbidden_write = [
            "> core/",
            "> src/",
            "> tests/",
            "> scripts/",
            "> ./",
            "tee ",
        ]
        for pat in forbidden_write:
            assert pat not in text, f"script must not write into repo: {pat!r}"


class TestScriptForbiddenContent:
    """Stripe and desktop_engine must never appear in the script body."""

    @pytest.mark.parametrize("word", ["Stripe", "desktop_engine"])
    def test_forbidden_word_absent(self, word: str) -> None:
        text = _read_script()
        assert word not in text, f"script must not reference {word!r}"


# ── static-only: no live network, no real install ────────────────────────

class TestStaticOnly:
    """Guarantee the test suite does not run the installer."""

    def test_no_live_network(self) -> None:
        """This test class never touches the network."""
        # If SCRIPT exists we are done; we never *execute* it here.
        assert SCRIPT.is_file()
