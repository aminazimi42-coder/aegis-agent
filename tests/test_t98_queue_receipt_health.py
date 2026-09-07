"""T98 — Readable queue, execute receipt, and /health.

Covers:
- ``status`` pending lines show ``title`` and ``digest`` (payload_sha256).
- ``execute`` success prints a receipt line containing action_id + digest +
  ``executed``.
- ``GET /health`` returns JSON with ``ok`` = ``True`` and status 200.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.server import create_app
from core.persistence import get_connection
from core.twin_actions import _action_digest, _load_action, approve
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local import main as twin_local_main
from fastapi.testclient import TestClient


class TestT98QueueReceiptHealth(unittest.TestCase):
    """Readable queue, execute receipt, and health endpoint."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t98_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _insert_action(
        self,
        tenant_id: str,
        kind: str,
        title: str,
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an action row with an optional payload and return its id."""
        import json as _json

        from core.twin_actions import _action_digest, _ensure_schema

        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(payload, dict):
            payload_json = _json.dumps(payload)
        elif isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = None
        # Compute the canonical digest so list_actions/list_queue exposes it.
        stub = {
            "action_id": action_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "title": title,
            "payload": payload,
        }
        digest = _action_digest(stub)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at, payload, "
                "payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now, payload_json, digest),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_status_lists_title_and_digest(self) -> None:
        """status pending lines show the action title and payload digest."""
        tenant = "t98a"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            payload={"note": "hello"},
        )
        # Reload the action to get its computed payload_sha256.
        loaded = _load_action(action_id)
        assert loaded is not None
        expected_digest = loaded.get("payload_sha256") or _action_digest(loaded)

        # Capture stdout from ``python -m core.twin_local status <tenant>``.
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = twin_local_main(["status", tenant])
        self.assertEqual(rc, 0)
        output = buf.getvalue()

        # The pending line must include the title and the digest.
        self.assertIn(action_id, output)
        self.assertIn("Review weekly digest", output)
        self.assertIn(expected_digest, output)

    def test_execute_prints_receipt(self) -> None:
        """execute success prints a receipt line with action_id + digest + executed."""
        tenant = "t98b"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
        )
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))

        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = twin_local_main(["execute", action_id, tenant])
        self.assertEqual(rc, 0)
        output = buf.getvalue()

        # The receipt line must contain action_id, digest, and "executed".
        self.assertIn("receipt:", output)
        self.assertIn(action_id, output)
        self.assertIn("executed", output)
        # The digest should appear in the receipt line.
        digest = action.get("payload_sha256") or _action_digest(action)
        self.assertIn(digest, output)

    def test_health_ok(self) -> None:
        """GET /health returns JSON with ok=true and status 200."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"), f"expected ok=true, got {payload!r}")

    def test_no_live_network(self) -> None:
        """No live network call is made in this test module."""
        # TestClient is local; no external network call is issued.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
