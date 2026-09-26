"""T215 — Optional Echo connect and Ahmad must-not.

Covers:

* ``test_default_engine_is_echo`` — with no env, ``engine_label`` is Echo.
* ``test_connect_no_server_stays_echo_fallback`` — connect with a base
  URL but no reachable server stays ``Echo (fallback)`` labeled, not silent.
* ``test_disconnect_returns_echo`` — disconnect clears the process override
  and returns Echo.
* ``test_ahmad_propose_contains_must_not`` — Ahmad's propose body contains
  a ``must-not`` / ``MUST NOT`` security gate line.
* ``test_secret_shape_redacted_on_ahmad_propose`` — a secret-shaped token
  in the propose text is redacted on the Ahmad card.
* ``test_six_specialists_still_only_six_names`` — the registry still has
  exactly six names; no seventh agent was added.
* ``test_core_has_no_stripe_token`` — no ``stripe`` substring in any
  ``core/*.py`` file.

No live network except ``TestClient``.  No ``xfail``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT215(unittest.TestCase):
    """T215 — optional Echo connect and Ahmad must-not line."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t215_")
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
    # 1. Default engine is Echo
    # ------------------------------------------------------------------ #

    def test_default_engine_is_echo(self) -> None:
        """With no LLM env set, engine_label returns 'Echo'."""
        from core.llm_provider import engine_label

        self.assertEqual(engine_label(), "Echo")

    # ------------------------------------------------------------------ #
    # 2. Connect with no server stays Echo (fallback) labeled
    # ------------------------------------------------------------------ #

    def test_connect_no_server_stays_echo_fallback(self) -> None:
        """Connect with a base URL but no reachable server stays Echo (fallback)."""
        client = self._client()
        resp = client.post(
            "/api/v1/twin/engine/connect",
            json={
                "tenant_id": "t215-fallback",
                "base_url": "http://127.0.0.1:1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["connected"])
        # The label must be Echo (fallback) — not silent, not HTTP.
        self.assertEqual(data["engine"], "Echo (fallback)")

    # ------------------------------------------------------------------ #
    # 3. Disconnect returns Echo
    # ------------------------------------------------------------------ #

    def test_disconnect_returns_echo(self) -> None:
        """Disconnect clears the process override and returns Echo."""
        client = self._client()
        # First connect to a dead URL.
        client.post(
            "/api/v1/twin/engine/connect",
            json={
                "tenant_id": "t215-disc",
                "base_url": "http://127.0.0.1:1",
            },
        )
        # Now disconnect — should return Echo.
        resp = client.post(
            "/api/v1/twin/engine/disconnect",
            json={"tenant_id": "t215-disc"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["connected"])
        self.assertEqual(data["engine"], "Echo")

    # ------------------------------------------------------------------ #
    # 4. Ahmad propose text contains must-not
    # ------------------------------------------------------------------ #

    def test_ahmad_propose_contains_must_not(self) -> None:
        """Ahmad's propose body contains a must-not / MUST NOT line."""
        from agents.ahmad.agent import AhmadAgent

        agent = AhmadAgent()
        body = agent._propose_body("review the access policy")
        lower = body.lower()
        self.assertTrue("must not" in lower or "must-not" in lower)

    # ------------------------------------------------------------------ #
    # 5. Secret shape redacted on Ahmad propose
    # ------------------------------------------------------------------ #

    def test_secret_shape_redacted_on_ahmad_propose(self) -> None:
        """A secret-shaped token in the propose text is redacted on the Ahmad card."""
        from agents.ahmad.agent import AhmadAgent

        secret = "sk-test-abcdefghijklmnopqrstuvwxyz0123456789"
        tenant = "t215-redact"
        agent = AhmadAgent()
        row = agent.propose(
            tenant,
            f"Review the token {secret}",
            batch_id=f"batch-{uuid4().hex[:8]}",
        )
        # The stored title and payload must not contain the raw secret.
        title = row.get("title", "")
        self.assertNotIn(secret, title)
        from core.twin_actions import _load_action

        action = _load_action(row["action_id"])
        assert action is not None
        payload = action.get("payload")
        if isinstance(payload, dict):
            body = payload.get("body", "")
        else:
            body = str(payload)
        self.assertNotIn(secret, body)
        self.assertIn("[REDACTED]", body)

    # ------------------------------------------------------------------ #
    # 6. Six specialists still only six names
    # ------------------------------------------------------------------ #

    def test_six_specialists_still_only_six_names(self) -> None:
        """The registry still has exactly six names; no seventh agent."""
        from core.agent_registry import AGENT_REGISTRY

        names = [a.name for a in AGENT_REGISTRY]
        self.assertEqual(len(names), 6)
        expected = {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"}
        self.assertEqual(set(names), expected)

    # ------------------------------------------------------------------ #
    # 7. core/ has no stripe token
    # ------------------------------------------------------------------ #

    def test_core_has_no_stripe_token(self) -> None:
        """No 'stripe' substring in any core/*.py file."""
        core_dir = _REPO_ROOT / "core"
        self.assertTrue(core_dir.is_dir())
        for p in core_dir.glob("*.py"):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("stripe", text, f"'stripe' found in {p}")


if __name__ == "__main__":
    unittest.main()
