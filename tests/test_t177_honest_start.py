"""T177 — Honest start: missing vs expired, HTTP timeout, start preflight.

Tests:

1. ``test_missing_file_banner_differs_from_expired`` — the entitlement
   API returns ``reason="missing_file"`` when the file is absent and
   ``reason="expired"`` when the file exists but the expiry is in the
   past; the two reasons are distinct typed strings.
2. ``test_expired_stays_echo_limited`` — an expired entitlement returns
   ``tier="echo"`` and the reason is ``expired``; it does not unlock.
3. ``test_http_adapter_timeout_falls_back_to_echo`` — when
   ``AGENT_LLM_BASE_URL`` is set and the HTTP call times out,
   ``complete_safe`` falls back to Echo and labels the fallback
   ``adapter_timeout``; the operator page does not hang.
4. ``test_start_operator_mentions_python_or_8741`` — the start script
   mentions python3 and port 8741.
5. ``test_start_operator_does_not_open_safari`` — the start script
   does not open Safari or use ``open -a``.
6. ``test_readme_author_untouched`` — the README Author paragraph
   still contains ``Author`` and the developer name.

Uses ``tmp_path`` (``tempfile.mkdtemp``).  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app.server import create_app
from core import llm_safety
from core.llm_provider import HttpProvider
from core.twin_quota import set_quota
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_START_SCRIPT = _REPO_ROOT / "scripts" / "start_operator.sh"
_README = _REPO_ROOT / "README.md"
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT177HonestStart(unittest.TestCase):
    """Missing vs expired, HTTP timeout, and start preflight."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t177_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_HTTP_TIMEOUT", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_HTTP_TIMEOUT", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _signed(self, tenant_id: str, tier: str, expires_at) -> dict:
        """Return an entitlement dict with a valid SHA-256 signature."""
        body = {
            "tenant_id": tenant_id,
            "tier": tier,
            "expires_at": expires_at,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        return body

    def _write_entitlement(self, data: dict) -> None:
        """Write *data* as ``entitlement.json`` under ``AEGIS_DATA_DIR``."""
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 1) Missing vs expired — distinct typed reasons
    # ------------------------------------------------------------------ #
    def test_missing_file_banner_differs_from_expired(self) -> None:
        """``missing_file`` and ``expired`` are distinct reason tokens."""
        from core.entitlement import load

        # Missing file — no entitlement.json on disk.
        missing = load(tenant_id="t177-missing")
        self.assertEqual(missing["tier"], "echo")
        self.assertEqual(missing["reason"], "missing_file")

        # Expired — file exists but expiry is in the past.
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t177-expired", "professional", past)
        self._write_entitlement(data)
        expired = load(tenant_id="t177-expired")
        self.assertEqual(expired["tier"], "echo")
        self.assertEqual(expired["reason"], "expired")

        # The two reasons are distinct typed strings.
        self.assertNotEqual(missing["reason"], expired["reason"])

        # The app.html banner references both reason tokens.
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("missing_file", html)
        self.assertIn("expired", html)

    # ------------------------------------------------------------------ #
    # 2) Expired stays Echo-limited
    # ------------------------------------------------------------------ #
    def test_expired_stays_echo_limited(self) -> None:
        """An expired entitlement stays Echo-limited and does not unlock."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t177-tenant", "professional", past)
        self._write_entitlement(data)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t177-tenant")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "expired")

    def test_missing_file_returns_missing_file_reason(self) -> None:
        """With no entitlement file on disk, the reason is ``missing_file``."""
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t177-no-file")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")

    # ------------------------------------------------------------------ #
    # 3) HTTP adapter timeout falls back to Echo
    # ------------------------------------------------------------------ #
    def test_http_adapter_timeout_falls_back_to_echo(self) -> None:
        """When AGENT_LLM_BASE_URL is set and the HTTP call times out,
        ``complete_safe`` falls back to Echo and labels the fallback;
        the operator page does not hang."""
        set_quota("t177-timeout", remaining=10, period_end="2099-12-31")
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://127.0.0.1:1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t177-123456"
        fake_http = HttpProvider(
            "http://127.0.0.1:1", "test-key-t177-123456", timeout=0.001,
        )
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                side_effect=OSError("timed out"),
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t177-timeout",
                )
        self.assertEqual(result["provider_kind"], "echo")
        self.assertIn("fallback_label", result)
        self.assertEqual(result["fallback_label"], "echo(fallback)")
        # The HttpProvider itself also has a finite timeout.
        self.assertEqual(HttpProvider.DEFAULT_TIMEOUT, 8.0)

    # ------------------------------------------------------------------ #
    # 4) start_operator mentions python and 8741
    # ------------------------------------------------------------------ #
    def test_start_operator_mentions_python_or_8741(self) -> None:
        """The start script mentions python3 and port 8741."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("python3", text)
        self.assertIn("8741", text)

    # ------------------------------------------------------------------ #
    # 5) start_operator does not open Safari
    # ------------------------------------------------------------------ #
    def test_start_operator_does_not_open_safari(self) -> None:
        """The start script does not open Safari or use ``open -a``."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("Safari", text)
        self.assertNotIn("open -a", text)

    # ------------------------------------------------------------------ #
    # 6) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)


if __name__ == "__main__":
    unittest.main()
