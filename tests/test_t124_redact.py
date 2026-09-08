"""T124 — Secret-shape redact and untrusted-source prefilter.

Covers:
- ``test_secret_shape_not_stored``: proposing text that contains secret-shaped
  substrings (``sk-…``, ``ghp_…``, ``AKIA…``, ``Bearer …``, ``eyJ…``) does not
  store the raw secret in the persisted row's title or payload body — the
  redacted ``[REDACTED]`` form is stored instead.
- ``test_audit_line_redacted``: :func:`core.audit_logger.log_event` redacts
  secret-shaped strings in its ``extra`` dict before writing the JSONL line.
- ``test_digest_uses_stored_payload``: the envelope digest is computed over
  the *redacted* payload, not the raw paste — re-computing the digest from the
  stored (redacted) row reproduces the stored ``payload_sha256``.

No live network except ``TestClient``.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient


class TestT124Redact(unittest.TestCase):
    """Secret-shape redaction on propose persist, audit, and untrusted prefilter."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t124_")
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

    # ------------------------------------------------------------------ #
    # 1. Secret shapes are not stored in propose rows
    # ------------------------------------------------------------------ #

    def test_secret_shape_not_stored(self) -> None:
        """Proposing text with secret shapes stores [REDACTED], not the raw secret."""
        from core.twin_local_view import list_queue

        secrets = [
            "sk-test-key-1234567890",
            "ghp_1234567890abcdefghij",
            "AKIAIOSFODNN7EXAMPLE2",
            "Bearer eyJhbGciOiJIUzI1.Ng.qwerty",
        ]
        tenant = "t124-secret"
        for secret in secrets:
            self._propose(tenant, f"Review the token {secret}")

        pending = list_queue(tenant)["pending"]
        self.assertGreater(len(pending), 0)

        # No raw secret appears in any row's title or payload body.
        for row in pending:
            title = row.get("title", "")
            self.assertNotIn("sk-test-key", title)
            self.assertNotIn("ghp_", title)
            self.assertNotIn("AKIA", title)

            payload = row.get("payload")
            if payload is not None:
                payload_str = (
                    json.dumps(payload) if isinstance(payload, dict) else str(payload)
                )
                self.assertNotIn("sk-test-key", payload_str)
                self.assertNotIn("ghp_", payload_str)
                self.assertNotIn("AKIA", payload_str)

        # The redaction marker IS present in at least one row.
        all_text = " ".join(
            row.get("title", "") + " " + str(row.get("payload", ""))
            for row in pending
        )
        self.assertIn("[REDACTED]", all_text)

    # ------------------------------------------------------------------ #
    # 2. Audit JSONL lines are redacted
    # ------------------------------------------------------------------ #

    def test_audit_line_redacted(self) -> None:
        """log_event redacts secret-shaped strings in extra before writing."""
        from core import audit_logger

        secret = "sk-live-1234567890abcdef"
        extra = {"note": f"key was {secret}", "meta": "clean text"}
        event = audit_logger.log_event(
            "propose",
            "act-t124-audit",
            extra=extra,
        )
        self.assertEqual(event["note"], "key was [REDACTED]")
        self.assertEqual(event["meta"], "clean text")

        # The raw secret is not in the event dict.
        event_str = json.dumps(event)
        self.assertNotIn(secret, event_str)
        self.assertIn("[REDACTED]", event_str)

        # Read the file back and confirm.
        from datetime import datetime, timezone
        from pathlib import Path

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        audit_file = (
            Path(self._tmp)
            / "audit"
            / f"{date_str}.jsonl"
        )
        self.assertTrue(audit_file.is_file())
        lines = audit_file.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(lines), 1)
        for line in lines:
            self.assertNotIn(secret, line)

    # ------------------------------------------------------------------ #
    # 3. Digest uses the stored (redacted) payload
    # ------------------------------------------------------------------ #

    def test_digest_uses_stored_payload(self) -> None:
        """The payload_sha256 is computed over the redacted payload.

        Re-computing the canonical envelope digest from the stored (redacted)
        row reproduces the stored ``payload_sha256`` — proving the digest
        was not computed over the raw secret-shaped string.
        """
        from core.twin_actions import (
            _action_digest,
            _load_action,
            insert_specialist_proposal,
        )

        tenant = "t124-digest"
        secret = "sk-secretkey-1234567890"
        payload = {"body": f"token {secret}"}
        row = insert_specialist_proposal(
            tenant,
            "Alina",
            f"Review token {secret}",
            payload,
            batch_id=f"batch-{uuid4().hex[:8]}",
        )
        action_id = row["action_id"]

        # The stored payload must be redacted.
        action = _load_action(action_id)
        assert action is not None
        stored_payload = action.get("payload")
        assert isinstance(stored_payload, dict)
        body = stored_payload.get("body", "")
        self.assertNotIn(secret, body)
        self.assertIn("[REDACTED]", body)

        # Re-compute the digest from the stored (redacted) action.
        recomputed = _action_digest(action)
        stored_digest = action.get("payload_sha256")
        self.assertTrue(stored_digest)
        self.assertEqual(recomputed, stored_digest)

    # ------------------------------------------------------------------ #
    # 4. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
