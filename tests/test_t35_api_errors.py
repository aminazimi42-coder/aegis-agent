"""T35 — Unified twin API error payload.

Covers:
- error_payload preserves detail == str(exc) unchanged.
- error_payload maps known messages to stable codes.
- error_payload attaches a non-empty request_id.
- FastAPI POST /api/v1/twin/resume/render without profile still 400 and
  detail contains "consented".
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.api_errors import error_payload, twin_value_error_response
from fastapi.testclient import TestClient


class TestT35ApiErrors(unittest.TestCase):
    """Unified twin error payload invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Unit-level
    # ------------------------------------------------------------------ #

    def test_error_payload_preserves_detail(self) -> None:
        payload = error_payload(ValueError("no consented profile"))
        self.assertEqual(payload["detail"], "no consented profile")

    def test_error_payload_known_message_maps_to_code(self) -> None:
        payload = error_payload(ValueError("no consented profile"))
        self.assertEqual(payload["code"], "TWIN_NO_PROFILE")

    def test_error_payload_unknown_message_falls_back(self) -> None:
        payload = error_payload(ValueError("something unexpected"))
        self.assertEqual(payload["code"], "TWIN_ERROR")

    def test_error_payload_has_nonempty_request_id(self) -> None:
        payload = error_payload(ValueError("no consented profile"))
        self.assertTrue(payload["request_id"])

    def test_error_payload_respects_given_request_id(self) -> None:
        payload = error_payload(ValueError("no consented profile"), request_id="abc123")
        self.assertEqual(payload["request_id"], "abc123")

    def test_twin_value_error_response_is_400(self) -> None:
        resp = twin_value_error_response(ValueError("no consented profile"))
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------ #
    # Integration-level
    # ------------------------------------------------------------------ #

    def test_resume_render_400_without_profile_contains_consented(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/resume/render",
            json={"tenant_id": "t35_no_profile"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("consented", body["detail"])
        self.assertIn("code", body)
        self.assertIn("request_id", body)


if __name__ == "__main__":
    unittest.main()
