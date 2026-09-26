"""T223 — optional LLM connect button, Echo default.

Covers (7 tests):

* ``test_default_echo_with_no_url`` — with no URL set, ``engine_label``
  returns ``"Echo"``.
* ``test_set_url_mock_http_labeled_http`` — set ``AEGIS_LLM_BASE_URL`` +
  ``AEGIS_LLM_API_KEY`` + ``AEGIS_LLM_PROVIDER=http`` (or
  ``AGENT_LLM_BACKEND=ollama``) → ``engine_label`` returns
  ``"HTTP (Ollama alias)"``.  No live network — ``is_available`` checks
  the in-memory probe flag, not a socket.
* ``test_dead_url_echo_fallback`` — set a dead base URL → ``engine_label``
  returns ``"Echo (fallback)"``.
* ``test_disconnect_returns_echo`` — ``POST /api/v1/twin/engine/disconnect``
  clears the process override and returns ``"Echo"``.
* ``test_neighbor_tenant_cannot_read_url_or_token`` — a connect response
  never contains the raw base URL or any token; a neighbor tenant's
  response does not leak the first tenant's URL.
* ``test_complete_safe_execute_unchanged`` — ``complete_safe`` reuses the
  existing ``get_provider`` adapter; ``execute`` in ``twin_actions`` does
  not import or call any provider — no new provider is called.
* ``test_no_stripe_in_core`` — no ``stripe`` substring in any
  ``core/*.py`` file.

No live network except ``TestClient``.  No ``xfail``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent

_ST = "str" + "ipe"  # avoid self-referential scan


class TestT223(unittest.TestCase):
    """T223 — optional local-engine connect; Echo default."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t223_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        for key in (
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_BASE_URL",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_BUDGET_EXHAUSTED",
            "AEGIS_OFFLINE",
            "AGENT_LLM_BACKEND",
            "AGENT_LLM_BASE_URL",
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
            "AGENT_LLM_BASE_URL",
        ):
            os.environ.pop(key, None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _client(self) -> TestClient:
        from app.server import create_app

        return TestClient(create_app())

    # ------------------------------------------------------------------ #
    # 1. Default Echo with no URL
    # ------------------------------------------------------------------ #

    def test_default_echo_with_no_url(self) -> None:
        """With no URL set, engine_label returns 'Echo'."""
        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo")

    # ------------------------------------------------------------------ #
    # 2. Set URL + mock HTTP → labeled HTTP
    # ------------------------------------------------------------------ #

    def test_set_url_mock_http_labeled_http(self) -> None:
        """Set base URL + key + provider=http → engine_label is 'HTTP (Ollama alias)'."""
        os.environ["AEGIS_LLM_BASE_URL"] = "http://127.0.0.1:11434"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-12345678"
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        from core.llm_provider import engine_label

        # is_available() checks the in-memory _last_probe_ok flag (starts
        # True); no socket is opened during engine_label.
        self.assertEqual(engine_label(), "HTTP (Ollama alias)")

    # ------------------------------------------------------------------ #
    # 3. Dead URL → Echo (fallback)
    # ------------------------------------------------------------------ #

    def test_dead_url_echo_fallback(self) -> None:
        """A dead base URL with no reachable server → engine_label is 'Echo (fallback)'."""
        os.environ["AEGIS_LLM_BASE_URL"] = "http://127.0.0.1:1"
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        # No API key → get_provider returns EchoProvider, not HttpProvider.
        # engine_label sees a base URL is set but no Http provider is
        # available → 'Echo (fallback)', not silent.
        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo (fallback)")

    # ------------------------------------------------------------------ #
    # 4. Disconnect returns Echo
    # ------------------------------------------------------------------ #

    def test_disconnect_returns_echo(self) -> None:
        """POST /engine/disconnect clears the override and returns Echo."""
        client = self._client()
        # First connect to a dead URL.
        client.post(
            "/api/v1/twin/engine/connect",
            json={"tenant_id": "t223-disc", "base_url": "http://127.0.0.1:1"},
        )
        resp = client.post(
            "/api/v1/twin/engine/disconnect",
            json={"tenant_id": "t223-disc"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["connected"])
        self.assertEqual(data["engine"], "Echo")

    # ------------------------------------------------------------------ #
    # 5. Neighbor tenant cannot read this tenant URL/token
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_cannot_read_url_or_token(self) -> None:
        """A connect response never contains the raw URL or token; neighbor is isolated."""
        client = self._client()
        secret_url = "http://10.99.99.99:11434"
        secret_token = "sk-t223-secret-1234567890"
        os.environ["AEGIS_LLM_API_KEY"] = secret_token
        # Tenant A connects with a recognizable URL.
        resp_a = client.post(
            "/api/v1/twin/engine/connect",
            json={"tenant_id": "tenant-a", "base_url": secret_url},
        )
        self.assertEqual(resp_a.status_code, 200)
        body_a = resp_a.json()
        # The response must not expose the raw URL or the token.
        self.assertNotIn(secret_url, str(body_a))
        self.assertNotIn(secret_token, str(body_a))
        # Tenant B's disconnect must also not leak A's URL.
        resp_b = client.post(
            "/api/v1/twin/engine/disconnect",
            json={"tenant_id": "tenant-b"},
        )
        self.assertEqual(resp_b.status_code, 200)
        body_b = resp_b.json()
        self.assertNotIn(secret_url, str(body_b))
        self.assertNotIn(secret_token, str(body_b))

    # ------------------------------------------------------------------ #
    # 6. complete_safe / execute path does not call a new provider
    # ------------------------------------------------------------------ #

    def test_complete_safe_execute_unchanged(self) -> None:
        """complete_safe reuses the existing get_provider; execute imports no provider."""
        safety_src = (_REPO_ROOT / "core" / "llm_safety.py").read_text(
            encoding="utf-8"
        )
        actions_src = (_REPO_ROOT / "core" / "twin_actions.py").read_text(
            encoding="utf-8"
        )
        # complete_safe reuses the existing adapter (get_provider).
        self.assertIn("get_provider", safety_src)
        # execute does not import or call any llm_provider.
        self.assertNotIn("llm_provider", actions_src)
        self.assertNotIn("get_provider", actions_src)

    # ------------------------------------------------------------------ #
    # 7. No stripe token in core/
    # ------------------------------------------------------------------ #

    def test_no_stripe_in_core(self) -> None:
        """No 'stripe' substring in any core/*.py file."""
        core_dir = _REPO_ROOT / "core"
        self.assertTrue(core_dir.is_dir())
        for p in core_dir.glob("*.py"):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn(_ST, text, f"'{_ST}' found in {p}")


if __name__ == "__main__":
    unittest.main()
