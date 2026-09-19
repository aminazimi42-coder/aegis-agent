"""T208 — Standing-order pin, tenant chip, and typed tenant switch.

Covers:

* ``test_html_has_standing_order_control`` — the operator page has a
  ``standing-order-pin`` control and a ``saveStandingOrderPin`` function.
* ``test_html_has_tenant_chip`` — the operator page has a
  ``tenant-chip`` element.
* ``test_pin_included_on_next_propose`` — when a pin is saved for a
  tenant, the next Propose includes the pin string in the task text.
* ``test_neighbor_pin_does_not_leak`` — a neighbor tenant's pin does
  not appear in the current tenant's propose text.
* ``test_switch_without_confirm_typed_deny`` — a switch without the
  exact ``SWITCH_TENANT`` confirm word returns the typed deny
  ``TENANT_SWITCH_CONFIRM_REQUIRED`` and does not switch.
* ``test_switch_loads_only_target_tenant_queue`` — after a valid
  switch, ``list_queue`` returns only the target tenant's queue.
* ``test_neighbor_queues_do_not_merge`` — source tenant cards stay on
  the source tenant; target tenant queue has only target rows.
* ``test_core_tree_has_no_stripe_token`` — no live Stripe secret token
  in ``core/``.
* ``test_readme_author_untouched`` — the README still has the Author
  paragraph.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

No live ``$HOME/.aegis`` is written; ``tmp_path`` is the data dir.
No xfail, no network, no cloud.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.standing_order import get_pin, pin_suffix, save_pin
from core.tenant_switch import switch_tenant
from core.twin_local_view import list_queue
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
_README = _REPO_ROOT / "README.md"
_NF = "not" + "arized"  # built at runtime to avoid self-trip


class TestT208Identity(unittest.TestCase):
    """Standing-order pin, tenant chip, and typed switch."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t208_")
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) HTML has standing-order control
    # ------------------------------------------------------------------ #
    def test_html_has_standing_order_control(self) -> None:
        """The operator page has ``standing-order-pin`` and
        ``saveStandingOrderPin``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("standing-order-pin", html)
        self.assertIn("saveStandingOrderPin", html)

    # ------------------------------------------------------------------ #
    # 2) HTML has tenant chip
    # ------------------------------------------------------------------ #
    def test_html_has_tenant_chip(self) -> None:
        """The operator page has a ``tenant-chip`` element."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("tenant-chip", html)

    # ------------------------------------------------------------------ #
    # 3) Pin included on next propose
    # ------------------------------------------------------------------ #
    def test_pin_included_on_next_propose(self) -> None:
        """When a pin is saved, the next Propose includes it in the
        task text.  The pin is local text — no execute."""
        tenant = "t208-pin-propose"
        save_pin(tenant, "prioritize inbox zero")
        # The pin suffix is appended to the task text.
        suffix = pin_suffix(tenant)
        self.assertIn("prioritize inbox zero", suffix)
        # Propose via the API — the pin should appear in the text.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        proposals = body.get("proposals", [])
        self.assertGreater(len(proposals), 0)
        # The pin string must appear in at least one proposal title.
        titles = [p.get("title", "") for p in proposals]
        self.assertTrue(
            any("prioritize inbox zero" in t for t in titles),
            f"pin not found in propose titles: {titles}",
        )

    # ------------------------------------------------------------------ #
    # 4) Neighbor pin does not leak
    # ------------------------------------------------------------------ #
    def test_neighbor_pin_does_not_leak(self) -> None:
        """A neighbor tenant's pin does not appear in the current
        tenant's propose text."""
        tenant_a = "t208-neighbor-a"
        tenant_b = "t208-neighbor-b"
        save_pin(tenant_a, "secret-alpha-pin")
        # tenant_b has no pin.
        self.assertEqual(get_pin(tenant_b), "")
        self.assertEqual(pin_suffix(tenant_b), "")
        # Propose for tenant_b — the neighbor's pin must not appear.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant_b, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        proposals = body.get("proposals", [])
        for p in proposals:
            title = p.get("title", "")
            self.assertNotIn(
                "secret-alpha-pin",
                title,
                f"neighbor pin leaked into tenant_b title: {title}",
            )

    # ------------------------------------------------------------------ #
    # 5) Switch without confirm is typed deny
    # ------------------------------------------------------------------ #
    def test_switch_without_confirm_typed_deny(self) -> None:
        """A switch without the exact ``SWITCH_TENANT`` confirm word
        returns the typed deny ``TENANT_SWITCH_CONFIRM_REQUIRED`` and
        does not switch."""
        result = switch_tenant("t208-target", "")
        self.assertEqual(result["code"], "TENANT_SWITCH_CONFIRM_REQUIRED")
        self.assertEqual(result["switched"], "false")
        # Wrong confirm word.
        result2 = switch_tenant("t208-target", "WRONG_WORD")
        self.assertEqual(result2["code"], "TENANT_SWITCH_CONFIRM_REQUIRED")
        self.assertEqual(result2["switched"], "false")

    # ------------------------------------------------------------------ #
    # 6) Switch loads only target tenant queue
    # ------------------------------------------------------------------ #
    def test_switch_loads_only_target_tenant_queue(self) -> None:
        """After a valid switch, ``list_queue`` returns only the target
        tenant's queue — not the source tenant's cards."""
        from core.twin_actions import insert_specialist_proposal

        source = "t208-switch-source"
        target = "t208-switch-target"
        # Insert a row for the source tenant.
        insert_specialist_proposal(
            source,
            "Alina",
            "Source action",
            {"body": "source"},
            batch_id="batch-src-01",
        )
        # Insert a row for the target tenant.
        insert_specialist_proposal(
            target,
            "Kian",
            "Target action",
            {"body": "target"},
            batch_id="batch-tgt-01",
        )
        # Before switch, source queue has the source row.
        src_q = list_queue(source)
        self.assertEqual(len(src_q["pending"]), 1)
        self.assertEqual(src_q["pending"][0]["title"], "Source action")
        # Target queue has the target row.
        tgt_q = list_queue(target)
        self.assertEqual(len(tgt_q["pending"]), 1)
        self.assertEqual(tgt_q["pending"][0]["title"], "Target action")
        # Switch to target.
        result = switch_tenant(target, "SWITCH_TENANT")
        self.assertEqual(result["switched"], "true")
        # After switch, list_queue for target still has only target rows.
        tgt_q2 = list_queue(target)
        self.assertEqual(len(tgt_q2["pending"]), 1)
        self.assertEqual(tgt_q2["pending"][0]["title"], "Target action")
        # Source queue still has only source rows — no merge.
        src_q2 = list_queue(source)
        self.assertEqual(len(src_q2["pending"]), 1)
        self.assertEqual(src_q2["pending"][0]["title"], "Source action")

    # ------------------------------------------------------------------ #
    # 7) Neighbor queues do not merge
    # ------------------------------------------------------------------ #
    def test_neighbor_queues_do_not_merge(self) -> None:
        """Source tenant cards stay on the source tenant; target tenant
        queue has only target rows.  No queue merge."""
        from core.twin_actions import insert_specialist_proposal

        tenant_a = "t208-no-merge-a"
        tenant_b = "t208-no-merge-b"
        insert_specialist_proposal(
            tenant_a,
            "Alina",
            "Action A",
            {"body": "a"},
            batch_id="batch-na-01",
        )
        insert_specialist_proposal(
            tenant_b,
            "Kian",
            "Action B",
            {"body": "b"},
            batch_id="batch-nb-01",
        )
        # list_queue for tenant_a has only A.
        qa = list_queue(tenant_a)
        titles_a = [r["title"] for r in qa["pending"]]
        self.assertEqual(titles_a, ["Action A"])
        # list_queue for tenant_b has only B.
        qb = list_queue(tenant_b)
        titles_b = [r["title"] for r in qb["pending"]]
        self.assertEqual(titles_b, ["Action B"])
        # No cross-contamination.
        self.assertNotIn("Action B", titles_a)
        self.assertNotIn("Action A", titles_b)

    # ------------------------------------------------------------------ #
    # 8) core/ has no live Stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """No live Stripe secret token (``sk_live_`` + 24+ chars) in
        core/."""
        core_dir = _REPO_ROOT / "core"
        pattern = re.compile(r"sk_live_[A-Za-z0-9]{24,}")
        offenders: list[str] = []
        for py in core_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                offenders.append(f"{py.name}: {m.group()}")
        self.assertEqual(offenders, [], f"Stripe live token in core/: {offenders}")

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
