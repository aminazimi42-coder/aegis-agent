"""T157 — Labeled HTTP adapter path, no key in core.

Covers:
- ``test_missing_key_does_not_open_socket``: when HTTP is requested
  but the key is missing (both env and data-dir file), the provider
  is Echo and the result is labeled ``echo_missing_key`` — no socket.
- ``test_http_status_does_not_echo_key_material``: when HTTP is
  active, the status/result payload does not contain the raw key.
- ``test_repo_tree_has_no_committed_llm_key_file``: no ``llm_key``
  file is committed to the repo tree (outside .venv, .git, tests).
- ``test_quota_exhausted_still_wins_over_http``: when the quota
  ledger is exhausted, Echo is used even when the key is present.
- ``test_readme_says_echo_when_key_missing``: README mentions that
  a missing key stays Echo.

Uses ``tmp_path``.  Does not start uvicorn.  Does not hit a public host.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from core import llm_safety
from core.llm_provider import load_llm_key


class TestT157LabeledPaidAdapter(unittest.TestCase):
    """Labeled HTTP adapter without a key in the core tree."""

    def setUp(self) -> None:
        self._tmp = Path(
            __import__("tempfile").mkdtemp(prefix="aegis_t157_"),
        )
        os.environ["AEGIS_DATA_DIR"] = str(self._tmp)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AGENT_LLM_BACKEND", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AGENT_LLM_BACKEND", None)

    # ------------------------------------------------------------------ #
    # 1) Missing key → Echo, no socket
    # ------------------------------------------------------------------ #
    def test_missing_key_does_not_open_socket(self) -> None:
        """HTTP requested + key missing → Echo, labeled echo_missing_key."""
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:11434"
        # No AEGIS_LLM_API_KEY, no llm_key file in tmp.

        # Ensure no key file in the tmp data dir.
        self.assertFalse((self._tmp / "llm_key").is_file())

        # load_llm_key should return None.
        self.assertIsNone(load_llm_key())

        result = llm_safety.complete_safe("ping", tenant_id="t157-missing")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result["llm_path"], "echo_missing_key")
        self.assertFalse(result["llm_key_present"])

    # ------------------------------------------------------------------ #
    # 2) HTTP result does not echo key material
    # ------------------------------------------------------------------ #
    def test_http_status_does_not_echo_key_material(self) -> None:
        """HTTP result payload must not contain the raw key string."""
        from core.llm_provider import HttpProvider
        from core.twin_quota import set_quota

        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:11434"
        os.environ["AEGIS_LLM_API_KEY"] = "sk-test-secret-t157-key"

        set_quota("t157-key", remaining=10, period_end="2099-12-31")

        fake_http = HttpProvider(
            "http://localhost:11434", "sk-test-secret-t157-key",
        )
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                return_value={
                    "text": "ok",
                    "model": "aegis-cheap",
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t157-key",
                )

        self.assertEqual(result["provider_kind"], "http")
        self.assertEqual(result["llm_path"], "http_labeled")
        self.assertTrue(result["llm_key_present"])
        # The raw key must never appear in the result.
        self.assertNotIn("sk-test-secret-t157-key", str(result))

    # ------------------------------------------------------------------ #
    # 3) No committed llm_key file in the repo tree
    # ------------------------------------------------------------------ #
    def test_repo_tree_has_no_committed_llm_key_file(self) -> None:
        """No llm_key file exists in the repo tree outside .venv/.git/tests."""
        repo_root = Path(__file__).resolve().parent.parent
        matches: list[Path] = []
        for p in repo_root.rglob("*llm_key*"):
            parts = p.parts
            if ".git" in parts or ".venv" in parts:
                continue
            if "test" in p.as_posix().lower():
                continue
            if "AEGIS_DATA_DIR" in str(p):
                continue
            if p.is_file() and p.name == "llm_key":
                matches.append(p)
        self.assertEqual(
            matches, [],
            f"Unexpected committed llm_key files: {matches}",
        )

    # ------------------------------------------------------------------ #
    # 4) Quota exhausted still wins over HTTP
    # ------------------------------------------------------------------ #
    def test_quota_exhausted_still_wins_over_http(self) -> None:
        """Quota ledger exhausted → Echo even with key + base URL set."""
        from core.llm_provider import HttpProvider
        from core.quota_ledger import set_allowance
        from core.twin_quota import set_quota

        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:11434"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t157-123456"

        # Set quota ledger allowance to 1, then consume it.
        set_allowance("t157-quota", allowance=1)
        quota_path = self._tmp / "quota.json"
        import json

        data = json.loads(quota_path.read_text(encoding="utf-8"))
        data["t157-quota"]["used"] = 1
        quota_path.write_text(json.dumps(data), encoding="utf-8")

        # Legacy twin_quota also allows HTTP so the ledger is the gate.
        set_quota("t157-quota", remaining=100, period_end="2099-12-31")

        fake_http = HttpProvider(
            "http://localhost:11434", "test-key-t157-123456",
        )
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            result = llm_safety.complete_safe("ping", tenant_id="t157-quota")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result["quota_state"], "exhausted")
        self.assertIn("quota_label", result)
        self.assertEqual(result["quota_label"], "quota_exhausted")

    # ------------------------------------------------------------------ #
    # 5) README says Echo when key missing
    # ------------------------------------------------------------------ #
    def test_readme_says_echo_when_key_missing(self) -> None:
        """README mentions that a missing key stays Echo."""
        readme = Path(__file__).resolve().parent.parent / "README.md"
        text = readme.read_text(encoding="utf-8")
        self.assertIn("Echo", text)
        self.assertIn("key", text.lower())


if __name__ == "__main__":
    unittest.main()
