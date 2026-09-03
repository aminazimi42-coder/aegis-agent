"""T16 — LLM secret isolation and complete-safe ledger.

Verifies:
- complete_safe with a prompt containing the AEGIS_LLM_API_KEY value:
  returned text must not contain the raw key (Echo would otherwise echo it).
- redact_secrets replaces the key with ``***``.
- core/llm_safety.py source contains no hardcoded ``sk-`` key.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from core import llm_safety
from core.llm_safety import complete_safe, redact_secrets

_FAKE_KEY = "sk-t16-redacted-test-key-0123456789"


class TestT16LLMSecretIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ["AEGIS_LLM_API_KEY"] = _FAKE_KEY

    def tearDown(self):
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_complete_safe_redacts_key_from_output(self):
        """complete_safe prompt with the key: returned text must not contain it."""
        prompt = f"use {_FAKE_KEY} for the request"
        result = complete_safe(prompt, tenant_id="t16")
        self.assertNotIn(_FAKE_KEY, result["text"])
        # The Echo provider echoes the (redacted) prompt, so '***' should appear.
        self.assertIn("***", result["text"])

    def test_redact_secrets_replaces_key(self):
        """redact_secrets replaces the key with '***'."""
        text = f"token={_FAKE_KEY}"
        redacted = redact_secrets(text)
        self.assertNotIn(_FAKE_KEY, redacted)
        self.assertIn("***", redacted)

    def test_source_has_no_hardcoded_sk_key(self):
        """core/llm_safety.py source does not contain a literal 'sk-' string."""
        source = pathlib.Path(llm_safety.__file__).read_text()
        self.assertNotIn("sk-", source)


if __name__ == "__main__":
    unittest.main()
