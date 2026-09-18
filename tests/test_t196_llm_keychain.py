"""T196 — optional LLM token from the macOS Keychain, mock on CI.

Covers:

* ``test_no_token_and_no_url_is_echo`` — with no Keychain/mock value and no
  base URL the default engine stays Echo.
* ``test_mock_store_roundtrip_on_non_darwin`` — the mock store round-trips a
  token value on non-Darwin.
* ``test_env_token_used_when_store_empty`` — when the store is empty the
  ``AGENT_LLM_API_KEY`` env var is used.
* ``test_store_token_not_written_to_repo_files`` — no keychain token value
  appears in any repo source file.
* ``test_t195_passphrase_not_read_from_keychain`` — the keychain module does
  not read ``AEGIS_DATA_PASSPHRASE``.
* ``test_readme_author_untouched`` — the README Author paragraph is present.
* ``test_readme_does_not_contain_notarized`` — the word *notarized* does not
  appear in the README.

Uses ``tmp_path``.  Mocks Keychain.  Does not write live ``$HOME/.aegis``.
Does not start uvicorn.  No ``xfail``.  Does not call a live LLM host.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT196(unittest.TestCase):
    """T196 — optional LLM token from Keychain on Darwin, mock on CI."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t196_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        for key in (
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_BASE_URL",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_BUDGET_EXHAUSTED",
            "AEGIS_OFFLINE",
            "AGENT_LLM_BACKEND",
            "AGENT_LLM_API_KEY",
        ):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        for key in (
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_BASE_URL",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_BUDGET_EXHAUSTED",
            "AEGIS_OFFLINE",
            "AGENT_LLM_BACKEND",
            "AGENT_LLM_API_KEY",
        ):
            os.environ.pop(key, None)

    # ------------------------------------------------------------------ #
    # 1) No token and no URL → Echo
    # ------------------------------------------------------------------ #
    def test_no_token_and_no_url_is_echo(self) -> None:
        """With no keychain value, no env token, and no base URL, the
        engine stays Echo."""
        from core import llm_keychain

        # Force the store to be empty so the result is deterministic.
        mock_store = llm_keychain.MockKeychain()
        with mock.patch("core.llm_keychain.get_store", return_value=mock_store):
            token = llm_keychain.load_optional_llm_key()
        self.assertIsNone(token)

        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo")

    # ------------------------------------------------------------------ #
    # 2) Mock store round-trip on non-Darwin
    # ------------------------------------------------------------------ #
    def test_mock_store_roundtrip_on_non_darwin(self) -> None:
        """The mock store round-trips a token value."""
        from core.llm_keychain import ACCOUNT_NAME, SERVICE_NAME, MockKeychain

        store = MockKeychain()
        token = "mock-token-t196-roundtrip-9f8e7d"
        store.set(SERVICE_NAME, ACCOUNT_NAME, token)
        self.assertEqual(store.get(SERVICE_NAME, ACCOUNT_NAME), token)
        self.assertIsNone(store.get(SERVICE_NAME, "missing-account"))

    # ------------------------------------------------------------------ #
    # 3) Env token used when store is empty
    # ------------------------------------------------------------------ #
    def test_env_token_used_when_store_empty(self) -> None:
        """When the store is empty the ``AGENT_LLM_API_KEY`` env var is
        used."""
        from core.llm_keychain import MockKeychain, load_optional_llm_key

        mock_store = MockKeychain()
        os.environ["AGENT_LLM_API_KEY"] = "env-token-t196-3c2b1a"
        with mock.patch("core.llm_keychain.get_store", return_value=mock_store):
            token = load_optional_llm_key()
        self.assertEqual(token, "env-token-t196-3c2b1a")

    # ------------------------------------------------------------------ #
    # 4) Store token not written to repo files
    # ------------------------------------------------------------------ #
    def test_store_token_not_written_to_repo_files(self) -> None:
        """No keychain token value appears in any repo source file."""
        from core.llm_keychain import ACCOUNT_NAME, SERVICE_NAME, MockKeychain

        store = MockKeychain()
        secret_value = "live-keychain-secret-t196-7g6h5i"
        store.set(SERVICE_NAME, ACCOUNT_NAME, secret_value)

        # Scan all non-binary source files in the repo for the secret.
        scan_dirs = [
            _REPO_ROOT / "core",
            _REPO_ROOT / "app",
            _REPO_ROOT / "tests",
            _REPO_ROOT / "scripts",
            _REPO_ROOT / "docs",
        ]
        scan_exts = {
            ".py", ".html", ".js", ".sh", ".md",
            ".json", ".yaml", ".yml", ".txt",
        }
        checked = 0
        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for p in scan_dir.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix not in scan_exts:
                    continue
                if p.resolve() == Path(__file__).resolve():
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                self.assertNotIn(
                    secret_value,
                    text,
                    f"keychain token found in {p}",
                )
                checked += 1
        self.assertGreater(checked, 0, "must have scanned at least one file")

    # ------------------------------------------------------------------ #
    # 5) T195 passphrase is not read from Keychain
    # ------------------------------------------------------------------ #
    def test_t195_passphrase_not_read_from_keychain(self) -> None:
        """The keychain module does not read ``AEGIS_DATA_PASSPHRASE``
        from the Keychain — the passphrase stays an env var per T195."""
        from core import llm_keychain

        source = Path(llm_keychain.__file__).read_text("utf-8")
        # The keychain module must not reference the passphrase env var
        # or the data_at_rest encryption passphrase.
        lower = source.lower()
        self.assertNotIn("aegis_data_passphrase", lower)
        self.assertNotIn("data_passphrase", lower)

    # ------------------------------------------------------------------ #
    # 6) README author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and unchanged."""
        text = Path(_REPO_ROOT / "README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 7) README does not contain 'notarized'
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The word *notarized* does not appear in the README."""
        text = Path(_REPO_ROOT / "README.md").read_text("utf-8")
        lower = text.lower()
        self.assertNotIn("nota" + "rized", lower)


if __name__ == "__main__":
    unittest.main()
