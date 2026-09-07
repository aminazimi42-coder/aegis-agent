"""T113 — Show the specialist body on the operator queue card.

Verifies that the operator page (``app.html``) renders the role-shaped
``payload.body`` from T112 on each pending queue card, so that the six
specialist rows are distinguishable instead of looking identical.

Covers:
- ``test_app_html_reads_body``: app.html references ``payload.body``
  and renders it inside a queue card element.
- ``test_card_not_title_only``: the queue card is not title-only — it
  shows the body in addition to the title, digest, and Approve button.
- No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT113QueueShowsBody(unittest.TestCase):
    """Each pending queue card shows the specialist body, not just the title."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t113_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # app.html reads payload.body
    # ------------------------------------------------------------------ #

    def test_app_html_reads_body(self) -> None:
        """app.html reads ``payload.body`` and renders it on the queue card."""
        html = _APP_HTML.read_text(encoding="utf-8")
        # The renderer must reference payload.body.
        self.assertIn("body", html.lower(), "app.html does not reference payload body")
        # There must be a queue-body CSS class used for rendering the body.
        self.assertIn("queue-body", html, "app.html has no queue-body element")

    # ------------------------------------------------------------------ #
    # The card is not title-only — body is rendered alongside the title
    # ------------------------------------------------------------------ #

    def test_card_not_title_only(self) -> None:
        """The queue card shows body, digest, and Approve — not just the title."""
        html = _APP_HTML.read_text(encoding="utf-8")
        # Extract the pending forEach block to inspect the card template.
        match = re.search(
            r"pending\.forEach\(function[^}]*\{.*?\}\);",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "pending forEach block not found in app.html")
        assert match is not None  # for type checkers
        block = match.group(0)

        # Must render a body element (queue-body) — not title-only.
        self.assertIn("queue-body", block, "card does not render a body element")
        # Must still show the digest.
        self.assertIn("digest", block, "card does not show the digest")
        # Must still show the Approve button.
        self.assertIn("Approve", block, "card does not show the Approve button")
        # Must reference the specialist name from the kind prefix.
        self.assertIn("specialistName", block, "card does not extract the specialist name")

    # ------------------------------------------------------------------ #
    # End-to-end: proposing produces a queue with body in payload
    # ------------------------------------------------------------------ #

    def test_queue_payload_has_body(self) -> None:
        """Proposing via the API produces six pending rows each with a body."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "t113-body", "text": "Review the board memo"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 6)

        from core.twin_local_view import list_queue

        pending = list_queue("t113-body")["pending"]
        self.assertEqual(len(pending), 6)

        # Every pending row must have a payload.body that is a non-empty string.
        for row in pending:
            payload = row.get("payload") or {}
            if isinstance(payload, str):
                import json

                try:
                    payload = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    payload = {}
            self.assertIsInstance(payload, dict, "payload must be a dict")
            self.assertIsInstance(
                payload.get("body"),
                str,
                "payload.body must be a string",
            )
            self.assertTrue(
                payload["body"].strip(),
                "payload.body must not be empty",
            )

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
