"""T219 — Today desk digest + standing-order specialist pin.

Covers:

* ``test_today_digest_file_under_export`` — the digest file lands under
  ``AEGIS_DATA_DIR/export/today_<utc>.md``.
* ``test_pin_ahmad_visible_on_next_propose_hint`` — after pinning Ahmad,
  the next Propose response carries ``standing_order_hint`` with Ahmad.
* ``test_unknown_specialist_typed_deny`` — an unknown specialist name
  returns ``STANDING_ORDER_UNKNOWN``.
* ``test_forget_clears_pin`` — an empty ``specialist_name`` clears the
  pin; the next propose hint is empty.
* ``test_neighbor_pin_does_not_leak`` — a neighbor tenant's pin does
  not appear in this tenant's propose hint.
* ``test_no_auto_execute`` — pinning does not execute or approve; all
  six specialists still run; status stays ``proposed``.
* ``test_core_has_no_stripe`` — no Stripe token in ``core/``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.standing_order import (
    SPECIALIST_NAMES,
    StandingOrderUnknownError,
    clear_specialist_pin,
    get_specialist_pin,
    set_specialist_pin,
    specialist_pin_hint,
)
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


class TestT219TodayStanding(unittest.TestCase):
    """Today desk digest + standing-order specialist pin."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t219_")
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Today digest file under export
    # ------------------------------------------------------------------ #

    def test_today_digest_file_under_export(self) -> None:
        """The digest file lands under export/today_<utc>.md."""
        from core.today_digest import build_today_digest

        result = build_today_digest("t219_digest")
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertTrue(path.name.startswith("today_"))
        self.assertTrue(path.name.endswith(".md"))
        self.assertIn("export", str(path))
        # The file content contains the counts and Intact state.
        text = path.read_text("utf-8")
        self.assertIn("propose", text.lower())
        self.assertIn("approve", text.lower())
        self.assertIn("reject", text.lower())
        self.assertIn("Intact", text)
        # The counts dict is present in the result.
        self.assertIn("counts", result)
        self.assertIn("last_intact", result)

    def test_today_digest_via_api(self) -> None:
        """GET /api/v1/twin/today-digest/{tenant_id} builds the file."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/today-digest/t219_api")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("path", body)
        self.assertIn("counts", body)
        self.assertIn("last_intact", body)
        path = Path(body["path"])
        self.assertTrue(path.is_file())
        self.assertTrue(path.name.startswith("today_"))

    # ------------------------------------------------------------------ #
    # 2) Pin Ahmad visible on next propose hint
    # ------------------------------------------------------------------ #

    def test_pin_ahmad_visible_on_next_propose_hint(self) -> None:
        """After pinning Ahmad, the next Propose carries the hint."""
        set_specialist_pin("t219_pin", "Ahmad")
        # The hint function returns the pinned specialist.
        hint = specialist_pin_hint("t219_pin")
        self.assertIn("Ahmad", hint)
        # Propose via the API — the hint should appear.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={
                "tenant_id": "t219_pin",
                "text": "review security posture",
                "training": False,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("standing_order_hint", body)
        self.assertIn("Ahmad", body["standing_order_hint"])
        # All six specialists still ran — Ahmad pin does not silence.
        proposals = body.get("proposals", [])
        agents = {p.get("agent", "") for p in proposals}
        self.assertIn("Ahmad", agents)
        self.assertIn("Alina", agents)

    def test_pin_ahmad_via_api(self) -> None:
        """POST /api/v1/twin/standing-order/{tenant_id} pins Ahmad."""
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/standing-order/t219_api_pin",
            json={"specialist_name": "Ahmad"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], "pin_saved")
        self.assertEqual(body["specialist"], "Ahmad")
        # GET returns the pinned specialist.
        resp2 = client.get(
            "/api/v1/twin/standing-order/t219_api_pin"
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["specialist"], "Ahmad")

    # ------------------------------------------------------------------ #
    # 3) Unknown specialist typed deny
    # ------------------------------------------------------------------ #

    def test_unknown_specialist_typed_deny(self) -> None:
        """An unknown specialist name returns STANDING_ORDER_UNKNOWN."""
        # Direct function call raises the typed error.
        with self.assertRaises(StandingOrderUnknownError) as ctx:
            set_specialist_pin("t219_unknown", "Bob")
        self.assertEqual(ctx.exception.code, "STANDING_ORDER_UNKNOWN")
        # Via the API — returns the typed deny code.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/standing-order/t219_unknown_api",
            json={"specialist_name": "Bob"},
        )
        body = resp.json()
        self.assertEqual(body["code"], "STANDING_ORDER_UNKNOWN")
        # The pin was not stored.
        self.assertEqual(get_specialist_pin("t219_unknown_api"), "")

    def test_all_six_names_accepted(self) -> None:
        """Each of the six specialist names is accepted."""
        for i, name in enumerate(SPECIALIST_NAMES):
            tenant = f"t219_name_{i}"
            stored = set_specialist_pin(tenant, name)
            self.assertEqual(stored, name)
            self.assertEqual(get_specialist_pin(tenant), name)

    # ------------------------------------------------------------------ #
    # 4) Forget clears pin
    # ------------------------------------------------------------------ #

    def test_forget_clears_pin(self) -> None:
        """An empty specialist_name clears the pin."""
        set_specialist_pin("t219_forget", "Ahmad")
        self.assertEqual(get_specialist_pin("t219_forget"), "Ahmad")
        # Clear via the API — omit specialist_name so the model
        # default (empty string) applies and the middleware does not
        # trip on an empty-string body field.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/standing-order/t219_forget",
            json={},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], "pin_cleared")
        # The pin is gone.
        self.assertEqual(get_specialist_pin("t219_forget"), "")
        self.assertEqual(specialist_pin_hint("t219_forget"), "")
        # Clear via the direct function too.
        set_specialist_pin("t219_forget2", "Amin")
        clear_specialist_pin("t219_forget2")
        self.assertEqual(get_specialist_pin("t219_forget2"), "")

    # ------------------------------------------------------------------ #
    # 5) Neighbor pin does not leak
    # ------------------------------------------------------------------ #

    def test_neighbor_pin_does_not_leak(self) -> None:
        """A neighbor tenant's pin does not appear in this tenant."""
        set_specialist_pin("t219_neighbor_a", "Ahmad")
        # Tenant B has no pin.
        self.assertEqual(get_specialist_pin("t219_neighbor_b"), "")
        self.assertEqual(specialist_pin_hint("t219_neighbor_b"), "")
        # Propose for tenant B — the hint should be empty, not Ahmad.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={
                "tenant_id": "t219_neighbor_b",
                "text": "review tasks",
                "training": False,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("standing_order_hint", ""), "")
        # Ahmad does not appear in B's hint.
        self.assertNotIn("Ahmad", body.get("standing_order_hint", ""))

    # ------------------------------------------------------------------ #
    # 6) No auto-execute
    # ------------------------------------------------------------------ #

    def test_no_auto_execute(self) -> None:
        """Pinning does not execute or approve; all six still run."""
        set_specialist_pin("t219_noexec", "Ahmad")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={
                "tenant_id": "t219_noexec",
                "text": "review security",
                "training": False,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        proposals = body.get("proposals", [])
        # All six specialists ran.
        self.assertEqual(len(proposals), 6)
        # Every proposal is still 'proposed' — no auto-approve, no
        # auto-execute.
        for p in proposals:
            self.assertEqual(p["status"], "proposed")
        # The six names are exactly the allowed set — no seventh agent.
        names = {p["agent"] for p in proposals}
        self.assertEqual(names, set(SPECIALIST_NAMES))

    # ------------------------------------------------------------------ #
    # 7) core/ has no Stripe token
    # ------------------------------------------------------------------ #

    def test_core_has_no_stripe(self) -> None:
        """No file under core/ contains the substring 'stripe'."""
        core_dir = Path("core")
        for p in core_dir.glob("*.py"):
            text = p.read_text("utf-8")
            self.assertNotRegex(
                text,
                r"(?i)stripe",
                f"'stripe' found in {p}",
            )

    # ------------------------------------------------------------------ #
    # 8) HTML has the new controls
    # ------------------------------------------------------------------ #

    def test_html_has_today_digest_button(self) -> None:
        """The operator page has a Today digest button next to evidence pack."""
        html = _APP_HTML.read_text("utf-8")
        self.assertIn("btn-today-digest", html)
        self.assertIn("exportTodayDigest", html)

    def test_html_has_standing_order_chip(self) -> None:
        """The operator page has Pin Ahmad / Clear pin controls."""
        html = _APP_HTML.read_text("utf-8")
        self.assertIn("btn-pin-ahmad", html)
        self.assertIn("pinAhmadSpecialist", html)
        self.assertIn("btn-clear-pin", html)
        self.assertIn("clearStandingOrderPin", html)
        self.assertIn("standing-order-chip-label", html)


if __name__ == "__main__":
    unittest.main()
