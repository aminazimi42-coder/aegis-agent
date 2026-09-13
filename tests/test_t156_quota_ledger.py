"""T156 — Quota ledger outside execute.

Covers:

* ``test_missing_file_remaining_is_zero``: when no ``quota.json``
  exists, ``remaining`` is 0 (Echo-limited, not an implicit paid pool).
* ``test_increment_stops_at_zero``: ``increment`` adds one ``used``
  unit only when ``remaining > 0``; once exhausted it returns 0 and
  does not go negative.
* ``test_exhausted_forces_echo_even_if_http_configured``: when
  ``exhausted`` is True, ``complete_safe`` uses the Echo provider even
  when ``AGENT_LLM_BASE_URL`` is set and the result is labeled
  ``quota_exhausted``.
* ``test_execute_does_not_increment_quota``: calling
  ``twin_actions.execute`` does not change the quota ledger's ``used``
  value — counting happens outside execute.
* ``test_quota_module_does_not_import_stripe``: the quota ledger
  module source does not contain the word ``stripe``.

Uses ``tmp_path``.  Does not write the developer's real
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock


class TestT156QuotaLedger(unittest.TestCase):
    """Local quota ledger lives under AEGIS_DATA_DIR and counts outside execute."""

    def setUp(self) -> None:
        self._tmp = Path(
            __import__("tempfile").mkdtemp(prefix="aegis_t156_"),
        )
        os.environ["AEGIS_DATA_DIR"] = str(self._tmp)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    # ------------------------------------------------------------------ #
    # 1) Missing file → remaining is zero
    # ------------------------------------------------------------------ #
    def test_missing_file_remaining_is_zero(self) -> None:
        """When no quota.json exists, remaining is 0 (Echo-limited)."""
        from core.quota_ledger import exhausted, quota_state, remaining

        self.assertEqual(remaining("t156-missing"), 0)
        self.assertTrue(exhausted("t156-missing"))
        self.assertEqual(quota_state("t156-missing"), "unset")

    # ------------------------------------------------------------------ #
    # 2) Increment stops at zero
    # ------------------------------------------------------------------ #
    def test_increment_stops_at_zero(self) -> None:
        """increment adds one used unit only when remaining > 0."""
        from core.quota_ledger import (
            exhausted,
            increment,
            remaining,
            set_allowance,
        )

        set_allowance("t156-inc", allowance=3)
        self.assertEqual(remaining("t156-inc"), 3)

        # Increment 3 times — should reach 0.
        r1 = increment("t156-inc")
        self.assertEqual(r1, 2)
        r2 = increment("t156-inc")
        self.assertEqual(r2, 1)
        r3 = increment("t156-inc")
        self.assertEqual(r3, 0)

        # Now exhausted; further increments return 0.
        self.assertTrue(exhausted("t156-inc"))
        r4 = increment("t156-inc")
        self.assertEqual(r4, 0)
        self.assertEqual(remaining("t156-inc"), 0)

    # ------------------------------------------------------------------ #
    # 3) Exhausted forces Echo even if HTTP configured
    # ------------------------------------------------------------------ #
    def test_exhausted_forces_echo_even_if_http_configured(self) -> None:
        """When exhausted, complete_safe uses Echo even with HTTP env."""
        from core import llm_safety
        from core.llm_provider import HttpProvider
        from core.quota_ledger import exhausted, set_allowance

        # Set allowance to 1, then consume it to exhaust.
        set_allowance("t156-echo", allowance=1)
        # Write the used to 1 so remaining is 0.
        quota_path = Path(self._tmp) / "quota.json"
        data = json.loads(quota_path.read_text(encoding="utf-8"))
        data["t156-echo"]["used"] = 1
        quota_path.write_text(json.dumps(data), encoding="utf-8")

        self.assertTrue(exhausted("t156-echo"))

        # Configure HTTP provider env so get_provider() would return Http.
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:0"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-12345678"

        # Also set a twin_quota remaining > 0 so the *legacy* quota
        # gate does not force echo — the *ledger* gate must be what
        # forces it.
        from core.twin_quota import set_quota

        set_quota("t156-echo", remaining=100, period_end="2099-12-31")

        # Patch get_provider to return an HttpProvider so we prove the
        # ledger gate — not the provider config — forces Echo.
        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            result = llm_safety.complete_safe("ping", tenant_id="t156-echo")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result["quota_state"], "exhausted")
        self.assertIn("quota_label", result)
        self.assertEqual(result["quota_label"], "quota_exhausted")

    # ------------------------------------------------------------------ #
    # 4) Execute does not increment quota
    # ------------------------------------------------------------------ #
    def test_execute_does_not_increment_quota(self) -> None:
        """Calling twin_actions.execute does not change the ledger's used."""
        from core.quota_ledger import remaining, set_allowance
        from core.twin_actions import (
            _action_digest,
            _load_action,
            approve,
            execute,
            propose_actions,
        )
        from core.twin_interview import QUESTIONS, answer, commit, start_session

        # Set up a tenant with a quota allowance.
        set_allowance("t156-exec", allowance=10)
        before = remaining("t156-exec")

        # Build a real action via interview + propose.
        tenant = "t156-exec"
        session = start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)

        actions = propose_actions(tenant)
        self.assertGreaterEqual(len(actions), 1)
        action = actions[0]
        action_id = action["action_id"]

        # Approve then execute.
        _a = _load_action(action_id)
        assert _a is not None
        approve(action_id, tenant, "tester", _action_digest(_a))
        execute(action_id, tenant)

        # Quota remaining must be unchanged after execute.
        after = remaining("t156-exec")
        self.assertEqual(before, after)

    # ------------------------------------------------------------------ #
    # 5) Quota module does not import Stripe
    # ------------------------------------------------------------------ #
    def test_quota_module_does_not_import_stripe(self) -> None:
        """core/quota_ledger.py source does not contain 'stripe'."""
        source = Path("core/quota_ledger.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "stripe",
            source.lower(),
            "quota_ledger.py must not contain 'stripe'",
        )


if __name__ == "__main__":
    unittest.main()
