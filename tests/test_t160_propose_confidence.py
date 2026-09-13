"""T160 — Confidence on propose card.

Tests:
1. Every propose payload includes a ``confidence`` integer in 0–100.
2. When confidence is below the threshold (40) the payload includes a
   short English clarifying question.
3. A low-confidence row does not execute — it stays ``proposed`` and
   ``execute()`` raises ``PermissionError``.
4. A high-confidence row still requires explicit Approve before
   ``execute()`` succeeds.
5. README mentions the confidence feature.

No uvicorn.  Uses ``tmp_path``.  Does not write the developer's real
``$HOME/.aegis``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestT160ProposeConfidence(unittest.TestCase):
    """Propose cards carry a deterministic 0–100 confidence integer."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t160_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _client(self) -> TestClient:
        from app.server import create_app

        return TestClient(create_app())

    def _propose(self, tenant_id: str, text: str) -> dict:
        client = self._client()
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant_id, "text": text},
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def _pending(self, tenant_id: str) -> list[dict]:
        from core.twin_local_view import list_queue

        return list_queue(tenant_id)["pending"]

    # ------------------------------------------------------------------ #
    # 1) confidence is an int in 0–100
    # ------------------------------------------------------------------ #

    def test_propose_payload_includes_confidence_0_100(self) -> None:
        """Every propose response and queue row carries a 0–100 int."""
        body = self._propose("t160-conf", "Review the quarterly security audit")
        for p in body["proposals"]:
            self.assertIn("confidence", p)
            self.assertIsInstance(p["confidence"], int)
            self.assertGreaterEqual(p["confidence"], 0)
            self.assertLessEqual(p["confidence"], 100)

        # The queue rows also carry confidence.
        pending = self._pending("t160-conf")
        self.assertGreaterEqual(len(pending), 1)
        for row in pending:
            self.assertIn("confidence", row)
            self.assertIsInstance(row["confidence"], int)
            self.assertGreaterEqual(row["confidence"], 0)
            self.assertLessEqual(row["confidence"], 100)

    # ------------------------------------------------------------------ #
    # 2) low confidence includes a clarifying question
    # ------------------------------------------------------------------ #

    def test_low_confidence_includes_clarifying_question(self) -> None:
        """When confidence < 40 the payload includes a clarifying question."""
        self._propose("t160-low", "x")
        pending = self._pending("t160-low")
        self.assertGreaterEqual(len(pending), 1)

        # At least one row should be low-confidence (short text, no
        # profile, echo path → 50 − 15 echo − 5 L1 = 30).
        low_rows = [r for r in pending if r["confidence"] < 40]
        self.assertGreaterEqual(
            len(low_rows), 1, "expected at least one low-confidence row"
        )
        for row in low_rows:
            payload = row.get("payload")
            if isinstance(payload, str):
                import json

                try:
                    payload = json.loads(payload)
                except (ValueError, TypeError):
                    payload = None
            self.assertIsInstance(payload, dict)
            self.assertIn("clarifying_question", payload)
            self.assertIsInstance(payload["clarifying_question"], str)
            self.assertTrue(payload["clarifying_question"].strip())

    # ------------------------------------------------------------------ #
    # 3) low confidence does not execute
    # ------------------------------------------------------------------ #

    def test_low_confidence_does_not_execute(self) -> None:
        """A low-confidence row stays proposed and execute() raises."""
        from core.twin_actions import execute

        self._propose("t160-noexec", "x")
        pending = self._pending("t160-noexec")
        low_rows = [r for r in pending if r["confidence"] < 40]
        self.assertGreaterEqual(len(low_rows), 1)
        row = low_rows[0]
        action_id = row["action_id"]

        # Must still be proposed (not approved, not executed).
        self.assertEqual(row["status"], "proposed")

        # execute() on a proposed row raises PermissionError.
        with self.assertRaises(PermissionError):
            execute(action_id, "t160-noexec")

    # ------------------------------------------------------------------ #
    # 4) high confidence still requires Approve
    # ------------------------------------------------------------------ #

    def test_high_confidence_still_requires_approve(self) -> None:
        """A high-confidence row cannot execute without explicit Approve."""
        from core.twin_actions import approve, execute

        self._propose("t160-high", "Review the quarterly security audit")
        pending = self._pending("t160-high")
        # At least one row should be high enough to be >= 40.
        high_rows = [r for r in pending if r["confidence"] >= 40]
        self.assertGreaterEqual(len(high_rows), 1)
        row = high_rows[0]
        action_id = row["action_id"]
        digest = row.get("payload_sha256", "")

        # Still proposed — cannot execute.
        with self.assertRaises(PermissionError):
            execute(action_id, "t160-high")

        # After explicit Approve with matching digest, execute works.
        approved = approve(
            action_id,
            "t160-high",
            "operator",
            digest,
        )
        self.assertEqual(approved["status"], "approved")
        result = execute(action_id, "t160-high")
        self.assertEqual(result["status"], "executed")

    # ------------------------------------------------------------------ #
    # 5) README mentions confidence
    # ------------------------------------------------------------------ #

    def test_readme_mentions_confidence(self) -> None:
        """README Now section mentions the confidence feature."""
        from pathlib import Path

        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("confidence", readme.lower())


if __name__ == "__main__":
    unittest.main()
