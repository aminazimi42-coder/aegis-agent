"""T162 — Status cost, HTTP adapter timeout, banner reason, extra redact.

Tests:
1. test_status_includes_duration_ms_and_http_token_cost
   — ``platform_status()`` returns ``duration_ms`` (int >= 0) and
     ``http_token_cost`` (int).
2. test_echo_http_token_cost_is_zero
   — On Echo (the default provider) ``http_token_cost`` is 0.
3. test_http_adapter_timeout_returns_echo_limited
   — An ``HttpProvider`` call that times out returns Echo-limited typed
     English; no worker hangs.
4. test_banner_reason_missing_file_or_expired
   — The offline banner HTML includes the existing reason token
     (``missing_file`` or ``expired``) when the entitlement degrades.
5. test_redact_bearer_and_pem_markers
   — The redactor redacts bearer tokens and PEM private-key begin markers.
6. test_readme_and_status_mention_entitlement_and_signed_export
   — README.md and STATUS.md mention ``entitlement`` + ``export`` and the
     test file exists.

No uvicorn.  Uses ``tmp_path`` (``tempfile.mkdtemp``).  Does not write the
developer's real ``$HOME/.aegis``.
"""

from __future__ import annotations

import os
import tempfile
import unittest


class TestT162StatusTimeoutBannerRedact(unittest.TestCase):
    """Status cost, adapter timeout, banner reason, and extra redaction."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t162_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_HTTP_TIMEOUT", None)

    # ------------------------------------------------------------------ #
    # 1) Status includes duration_ms and http_token_cost
    # ------------------------------------------------------------------ #

    def test_status_includes_duration_ms_and_http_token_cost(self) -> None:
        """``platform_status()`` returns ``duration_ms`` and
        ``http_token_cost`` as integers."""
        from core.platform_status import platform_status

        status = platform_status()
        self.assertIn("duration_ms", status)
        self.assertIn("http_token_cost", status)
        self.assertIsInstance(status["duration_ms"], int)
        self.assertIsInstance(status["http_token_cost"], int)
        self.assertGreaterEqual(status["duration_ms"], 0)

    # ------------------------------------------------------------------ #
    # 2) Echo http_token_cost is zero
    # ------------------------------------------------------------------ #

    def test_echo_http_token_cost_is_zero(self) -> None:
        """On Echo (default) ``http_token_cost`` is 0."""
        from core.platform_status import platform_status

        # No AEGIS_LLM_PROVIDER set → Echo is the default.
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        status = platform_status()
        self.assertEqual(status["http_token_cost"], 0)
        self.assertEqual(status["llm_provider"], "EchoProvider")

    # ------------------------------------------------------------------ #
    # 3) HTTP adapter timeout returns Echo-limited
    # ------------------------------------------------------------------ #

    def test_http_adapter_timeout_returns_echo_limited(self) -> None:
        """An ``HttpProvider`` call that times out returns Echo-limited
        typed English; the timeout is finite (default 8 seconds)."""
        from core.llm_provider import HttpProvider

        # Use a very short timeout and a dead host to trigger timeout.
        provider = HttpProvider(
            base_url="http://127.0.0.1:1",
            api_key="test-key-12345678",
            timeout=0.001,
        )
        # The default timeout should be 8 seconds (not 30).
        self.assertEqual(HttpProvider.DEFAULT_TIMEOUT, 8.0)
        # The configured timeout should be 0.001.
        self.assertAlmostEqual(provider._timeout, 0.001)

        result = provider.complete("hello", model="test", max_tokens=10)
        # On timeout, the provider falls back to Echo and returns a
        # deterministic echo response — not a hang.
        self.assertIsInstance(result, dict)
        self.assertIn("text", result)
        self.assertIn("model", result)
        # The echo text starts with ECHO.
        self.assertTrue(result["text"].startswith("ECHO"))

    # ------------------------------------------------------------------ #
    # 4) Banner reason: missing_file or expired
    # ------------------------------------------------------------------ #

    def test_banner_reason_missing_file_or_expired(self) -> None:
        """The offline banner HTML includes the existing reason token
        (``missing_file`` or ``expired``) when the entitlement degrades."""
        from pathlib import Path

        # The app.html banner includes a ``banner-reason`` element that
        # shows the reason token when it is ``missing_file`` or ``expired``.
        html_path = (
            Path(__file__).resolve().parent.parent
            / "desktop"
            / "macos"
            / "Aegis.app"
            / "Contents"
            / "Resources"
            / "app.html"
        )
        html = html_path.read_text(encoding="utf-8")
        # The banner-reason element exists in the HTML.
        self.assertIn("banner-reason", html)
        # The JS logic references both reason tokens.
        self.assertIn("missing_file", html)
        self.assertIn("expired", html)
        # The Echo-limited banner text includes the reason token.
        self.assertIn("Echo-limited", html)

    # ------------------------------------------------------------------ #
    # 5) Redact bearer and PEM markers
    # ------------------------------------------------------------------ #

    def test_redact_bearer_and_pem_markers(self) -> None:
        """The redactor redacts bearer tokens and PEM private-key begin
        markers."""
        from core.redact import redact

        # Bearer token (opaque, not sk-shaped)
        bearer_text = "Authorization: Bearer abcdefghijklmnop1234567890"
        redacted = redact(bearer_text)
        self.assertNotIn("abcdefghijklmnop1234567890", redacted)
        self.assertIn("[REDACTED]", redacted)

        # PEM private-key begin marker
        pem_text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        redacted_pem = redact(pem_text)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", redacted_pem)
        self.assertIn("[REDACTED]", redacted_pem)

        # EC private key also covered
        pem_ec = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEE..."
        redacted_ec = redact(pem_ec)
        self.assertNotIn("BEGIN EC PRIVATE KEY", redacted_ec)
        self.assertIn("[REDACTED]", redacted_ec)

        # redact_payload on a dict with bearer and PEM
        from core.redact import redact_payload

        payload = {
            "auth": "Bearer abcdefghijklmnop1234567890",
            "key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
        }
        result = redact_payload(payload)
        self.assertIn("[REDACTED]", result["auth"])
        self.assertIn("[REDACTED]", result["key"])

    # ------------------------------------------------------------------ #
    # 6) README and STATUS mention entitlement and signed export
    # ------------------------------------------------------------------ #

    def test_readme_and_status_mention_entitlement_and_signed_export(self) -> None:
        """README.md and STATUS.md mention ``entitlement`` and ``export``;
        the test file exists."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        readme = (repo_root / "README.md").read_text(encoding="utf-8")
        status = (repo_root / "STATUS.md").read_text(encoding="utf-8")
        lower_r = readme.lower()
        lower_s = status.lower()
        self.assertIn("entitlement", lower_r)
        self.assertIn("export", lower_r)
        self.assertIn("entitlement", lower_s)
        self.assertIn("export", lower_s)
        test_path = repo_root / "tests" / "test_t162_status_timeout_banner_redact.py"
        self.assertTrue(test_path.is_file())


if __name__ == "__main__":
    unittest.main()
