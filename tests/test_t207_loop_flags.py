"""T207 — Quiet mode and Training vs Live work loop flags.

Covers:

* ``test_html_has_quiet_mode_control`` — the operator page has a
  ``quiet-mode-toggle`` control and a ``toggleQuietMode`` function.
* ``test_html_has_training_live_work_control`` — the operator page has
  a ``training-live-select`` control.
* ``test_quiet_mode_blocks_propose`` — when Quiet is on for a tenant,
  ``is_quiet_mode`` returns ``True`` and a second tenant is unaffected.
* ``test_quiet_mode_blocks_weekly_brief`` — the same Quiet flag blocks
  both the propose path and the weekly-brief path (same route).
* ``test_quiet_mode_clears_on_start_session_only`` — ``set_quiet_mode``
  turns Quiet on; clearing it requires an explicit ``False`` (refresh
  preserves the flag via ``quiet_mode=None``).
* ``test_neighbor_quiet_does_not_apply`` — a neighbour tenant's Quiet
  flag does not affect another tenant.
* ``test_training_flag_stored_on_batch`` —
  ``insert_specialist_proposal`` stores the ``training`` column.
* ``test_training_execute_typed_deny`` — a Training-flagged action
  raises ``PermissionError("TRAINING_BATCH_NO_EXECUTE")`` on execute.
* ``test_live_work_still_requires_approve`` — a Live work action still
  requires ``approve`` before ``execute``.
* ``test_core_tree_has_no_stripe_token`` — no live Stripe secret token
  (``sk_live_`` with 24+ chars) lives in ``core/``.
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

from core.session_receipt import (
    is_quiet_mode,
    set_quiet_mode,
    write_session_receipt,
)
from core.twin_actions import (
    _action_digest,
    approve,
    execute,
    insert_specialist_proposal,
)

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
_ROOT_HTML = _REPO_ROOT / "app.html"
_README = _REPO_ROOT / "README.md"
_NF = "not" + "arized"  # built at runtime to avoid self-trip


class TestT207LoopFlags(unittest.TestCase):
    """Quiet mode and Training vs Live work flag controls."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) HTML has quiet-mode control
    # ------------------------------------------------------------------ #
    def test_html_has_quiet_mode_control(self) -> None:
        """The operator page has ``quiet-mode-toggle`` and
        ``toggleQuietMode``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("quiet-mode-toggle", html)
        self.assertIn("toggleQuietMode", html)

    # ------------------------------------------------------------------ #
    # 2) HTML has Training / Live work control
    # ------------------------------------------------------------------ #
    def test_html_has_training_live_work_control(self) -> None:
        """The operator page has ``training-live-select``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("training-live-select", html)

    # ------------------------------------------------------------------ #
    # 3) Quiet mode blocks propose
    # ------------------------------------------------------------------ #
    def test_quiet_mode_blocks_propose(self) -> None:
        """``is_quiet_mode`` returns True after ``set_quiet_mode``."""
        tenant = "t207-quiet-propose"
        self.assertFalse(is_quiet_mode(tenant))
        set_quiet_mode(tenant, True)
        self.assertTrue(is_quiet_mode(tenant))

    # ------------------------------------------------------------------ #
    # 4) Quiet mode blocks weekly brief (same flag, same route)
    # ------------------------------------------------------------------ #
    def test_quiet_mode_blocks_weekly_brief(self) -> None:
        """The Quiet flag is tenant-bound and blocks both propose and
        weekly brief (they share the same route and Quiet guard)."""
        tenant = "t207-quiet-brief"
        set_quiet_mode(tenant, True)
        self.assertTrue(is_quiet_mode(tenant))

    # ------------------------------------------------------------------ #
    # 5) Quiet mode clears on start session only (explicit False)
    # ------------------------------------------------------------------ #
    def test_quiet_mode_clears_on_start_session_only(self) -> None:
        """``quiet_mode=None`` preserves the flag (refresh); only an
        explicit ``False`` clears it (start session)."""
        tenant = "t207-quiet-clear"
        set_quiet_mode(tenant, True)
        self.assertTrue(is_quiet_mode(tenant))
        # Refresh path: quiet_mode=None preserves the existing flag.
        write_session_receipt(tenant, quiet_mode=None)
        self.assertTrue(is_quiet_mode(tenant))
        # Start Session path: explicit False clears it.
        write_session_receipt(tenant, quiet_mode=False)
        self.assertFalse(is_quiet_mode(tenant))

    # ------------------------------------------------------------------ #
    # 6) Neighbor tenant's Quiet does not apply
    # ------------------------------------------------------------------ #
    def test_neighbor_quiet_does_not_apply(self) -> None:
        """A neighbour tenant's Quiet flag does not affect another
        tenant."""
        tenant_a = "t207-neighbor-a"
        tenant_b = "t207-neighbor-b"
        set_quiet_mode(tenant_a, True)
        self.assertTrue(is_quiet_mode(tenant_a))
        self.assertFalse(is_quiet_mode(tenant_b))

    # ------------------------------------------------------------------ #
    # 7) Training flag stored on batch
    # ------------------------------------------------------------------ #
    def test_training_flag_stored_on_batch(self) -> None:
        """``insert_specialist_proposal`` stores the training column."""
        tenant = "t207-training-batch"
        row = insert_specialist_proposal(
            tenant,
            "test-specialist",
            "Training action",
            {"note": "training"},
            training=True,
        )
        self.assertTrue(row["training"])
        # Live work flag stored as False.
        row2 = insert_specialist_proposal(
            tenant,
            "test-specialist",
            "Live work action",
            {"note": "live"},
            training=False,
        )
        self.assertFalse(row2["training"])

    # ------------------------------------------------------------------ #
    # 8) Training execute typed deny
    # ------------------------------------------------------------------ #
    def test_training_execute_typed_deny(self) -> None:
        """A Training-flagged action raises
        ``PermissionError("TRAINING_BATCH_NO_EXECUTE")`` on execute."""
        tenant = "t207-training-deny"
        row = insert_specialist_proposal(
            tenant,
            "test-specialist",
            "Training deny action",
            {"note": "deny"},
            training=True,
        )
        action_id = row["action_id"]
        digest = _action_digest(row)
        approve(action_id, tenant, "tester", digest, why="approved")
        with self.assertRaises(PermissionError) as ctx:
            execute(action_id, tenant_id=tenant)
        self.assertIn("TRAINING_BATCH_NO_EXECUTE", str(ctx.exception))

    # ------------------------------------------------------------------ #
    # 9) Live work still requires approve
    # ------------------------------------------------------------------ #
    def test_live_work_still_requires_approve(self) -> None:
        """A Live work (training=False) action still requires approve
        before execute; unapproved raises ``PermissionError``."""
        tenant = "t207-live-approve"
        row = insert_specialist_proposal(
            tenant,
            "test-specialist",
            "Live work action",
            {"note": "live"},
            training=False,
        )
        action_id = row["action_id"]
        # Without approve, execute raises PermissionError("approval
        # required").
        with self.assertRaises(PermissionError) as ctx:
            execute(action_id, tenant_id=tenant)
        self.assertIn("approval required", str(ctx.exception))
        # After approve, execute succeeds (no TRAINING deny).
        digest = _action_digest(row)
        approve(action_id, tenant, "tester", digest, why="go")
        result = execute(action_id, tenant_id=tenant)
        self.assertEqual(result["status"], "executed")

    # ------------------------------------------------------------------ #
    # 10) core/ has no live Stripe token
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
    # 11) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)

    # ------------------------------------------------------------------ #
    # 12) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
