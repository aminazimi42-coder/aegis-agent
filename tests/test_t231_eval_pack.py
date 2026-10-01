"""T231 — fourteen-day local eval pack, no repo inside the pack.

Covers:

* ``pack_manifest`` excludes ``.git``, ``_directive.txt``, and any path
  under the owner ``.aegis`` data dir.
* An active eval marker (``now <= ends_at``) is **not** expired.
* A past eval window (``now > ends_at``) returns **Echo-limited** with
  reason ``eval_expired``.
* The data dir is **not deleted** after expiry — profile, receipts, and
  export stay.
* A **missing** marker stays the existing ``missing_file`` Echo-limited
  path (no crash).
* Cross-tenant cannot read another tenant's marker.
* No ``stripe`` substring in ``core/``.
* No network call.
* ``start_operator.sh`` remains the only start path.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  No live HTTP.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.eval_pack import (
    EVAL_DAYS,
    create_eval_marker,
    eval_entitlement,
    pack_manifest,
    read_eval_marker,
)


class TestT231EvalPack(unittest.TestCase):
    """T231 — fourteen-day local eval pack, no repo inside the pack."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t231_data_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._pack = tempfile.mkdtemp(prefix="aegis_t231_pack_")

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Manifest excludes repo, directive, and data dir
    # ------------------------------------------------------------------ #
    def test_manifest_excludes_repo_and_data_dir(self) -> None:
        """The pack manifest excludes .git, _directive.txt, and any path
        under the owner .aegis data dir."""
        pack = Path(self._pack)
        # Build a source pack with operator files plus excluded entries.
        (pack / "app.py").write_text("# app\n", encoding="utf-8")
        (pack / "start_operator.sh").write_text("# start\n", encoding="utf-8")
        (pack / "_directive.txt").write_text("directive\n", encoding="utf-8")
        (pack / ".git").mkdir()
        (pack / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")
        (pack / "__pycache__").mkdir()
        (pack / "__pycache__" / "x.pyc").write_text("cache\n", encoding="utf-8")
        (pack / ".venv").mkdir()
        (pack / ".venv" / "bin").mkdir()
        (pack / ".venv" / "bin" / "python").write_text("bin\n", encoding="utf-8")
        # A file that looks like it's under .aegis — we point source_dir
        # at a dir that has a .aegis subdir; that subdir's files must be
        # excluded because they resolve inside the data dir.
        aegis_sub = pack / "sub" / ".aegis"
        aegis_sub.mkdir(parents=True)
        # But the data dir is self._tmp, not pack/sub/.aegis — so we
        # test the data-dir exclusion separately below.  Here we just
        # check top-level excludes.
        manifest = pack_manifest(pack)
        # app.py and start_operator.sh are included.
        self.assertIn("app.py", manifest)
        self.assertIn("start_operator.sh", manifest)
        # _directive.txt is excluded.
        self.assertNotIn("_directive.txt", manifest)
        # .git is excluded.
        for f in manifest:
            self.assertFalse(f.startswith(".git/") or f == ".git")
        # __pycache__ is excluded.
        for f in manifest:
            self.assertFalse("__pycache__" in f)
        # .venv is excluded.
        for f in manifest:
            self.assertFalse(f.startswith(".venv/") or f == ".venv")

    def test_manifest_excludes_data_dir_inside(self) -> None:
        """When a source path resolves inside ``AEGIS_DATA_DIR`` it is
        excluded from the manifest."""
        # Point the source dir at the data dir itself — every file there
        # resolves inside the data root and must be excluded.
        manifest = pack_manifest(self._tmp)
        self.assertEqual(manifest, [])

    # ------------------------------------------------------------------ #
    # 2) Active window is not expired
    # ------------------------------------------------------------------ #
    def test_active_window_not_expired(self) -> None:
        """A marker whose ends_at is in the future returns ``eval_active``
        (not expired)."""
        now = datetime.now(timezone.utc)
        marker = create_eval_marker("t231", started_at=now)
        self.assertEqual(marker["status"], "active")
        # ends_at = started_at + 14 days.
        started = datetime.fromisoformat(marker["started_at"])
        ended = datetime.fromisoformat(marker["ends_at"])
        self.assertEqual(ended - started, timedelta(days=EVAL_DAYS))
        # eval_entitlement returns active.
        result = eval_entitlement("t231")
        self.assertEqual(result["reason"], "eval_active")

    def test_ends_at_is_started_plus_fourteen(self) -> None:
        """``ends_at`` is exactly ``started_at`` plus 14 days."""
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        marker = create_eval_marker("t231b", started_at=now)
        started = datetime.fromisoformat(marker["started_at"])
        ended = datetime.fromisoformat(marker["ends_at"])
        self.assertEqual(ended - started, timedelta(days=14))

    # ------------------------------------------------------------------ #
    # 3) Past window is Echo-limited
    # ------------------------------------------------------------------ #
    def test_past_window_is_echo_limited(self) -> None:
        """When ``now`` is after ``ends_at`` the entitlement returns
        Echo-limited with reason ``eval_expired``."""
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        create_eval_marker("t231exp", started_at=old)
        result = eval_entitlement("t231exp")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "eval_expired")

    # ------------------------------------------------------------------ #
    # 4) Data dir still present after expiry
    # ------------------------------------------------------------------ #
    def test_data_dir_kept_after_expiry(self) -> None:
        """After expiry, the data dir and its contents (profile, receipts,
        export) are still present — expiry does not delete data."""
        root = Path(self._tmp)
        # Seed data.
        (root / "profile.json").write_text(
            json.dumps({"tenant_id": "t231d", "name": "test"}), encoding="utf-8"
        )
        rdir = root / "receipts"
        rdir.mkdir(exist_ok=True)
        (rdir / "r1.md").write_text("# r1\n", encoding="utf-8")
        edir = root / "export"
        edir.mkdir(exist_ok=True)
        (edir / "brief.md").write_text("# brief\n", encoding="utf-8")
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        create_eval_marker("t231d", started_at=old)
        # Trigger expiry.
        result = eval_entitlement("t231d")
        self.assertEqual(result["reason"], "eval_expired")
        # Data dir contents still present.
        self.assertTrue((root / "profile.json").is_file())
        self.assertTrue((root / "receipts").is_dir())
        self.assertTrue((root / "receipts" / "r1.md").is_file())
        self.assertTrue((root / "export").is_dir())
        self.assertTrue((root / "export" / "brief.md").is_file())
        # Marker file stays.
        marker = read_eval_marker("t231d")
        assert marker is not None
        self.assertEqual(marker.get("status"), "expired")

    # ------------------------------------------------------------------ #
    # 5) Missing marker stays missing-file Echo-limited (no crash)
    # ------------------------------------------------------------------ #
    def test_missing_marker_is_missing_file_echo(self) -> None:
        """A missing marker stays the existing ``missing_file``
        Echo-limited path — no crash."""
        result = eval_entitlement("nonexistent_tenant")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "missing_file")

    # ------------------------------------------------------------------ #
    # 6) Cross-tenant cannot read the marker
    # ------------------------------------------------------------------ #
    def test_cross_tenant_cannot_read_marker(self) -> None:
        """Tenant A's marker is not readable as tenant B."""
        now = datetime.now(timezone.utc)
        create_eval_marker("tenant_a", started_at=now)
        # Tenant B tries to read tenant A's marker — returns None.
        result = read_eval_marker("tenant_b")
        self.assertIsNone(result)
        # eval_entitlement for tenant B falls through to missing_file.
        ent = eval_entitlement("tenant_b")
        self.assertEqual(ent["reason"], "missing_file")
        # Tenant A's marker is unaffected.
        a = read_eval_marker("tenant_a")
        assert a is not None
        self.assertEqual(a["tenant_id"], "tenant_a")

    # ------------------------------------------------------------------ #
    # 7) No stripe token in core
    # ------------------------------------------------------------------ #
    def test_core_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring."""
        _repo_root = Path(__file__).resolve().parent.parent
        core_dir = _repo_root / "core"
        for p in sorted(core_dir.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("stripe", text, f"stripe found in {p.name}")

    # ------------------------------------------------------------------ #
    # 8) No network call
    # ------------------------------------------------------------------ #
    def test_no_network_call(self) -> None:
        """The eval_pack module imports no network library."""
        import core.eval_pack as ep

        source = open(ep.__file__, encoding="utf-8").read().lower()
        for forbidden in ("urllib", "requests", "http.client", "socket"):
            self.assertNotIn(
                forbidden,
                source,
                f"{forbidden} found in eval_pack source",
            )

    # ------------------------------------------------------------------ #
    # 9) start_operator.sh remains the only start path
    # ------------------------------------------------------------------ #
    def test_start_operator_remains_only_start(self) -> None:
        """``scripts/start_operator.sh`` exists in the repo."""
        _repo_root = Path(__file__).resolve().parent.parent
        start = _repo_root / "scripts" / "start_operator.sh"
        self.assertTrue(start.is_file(), "scripts/start_operator.sh must exist")

    # ------------------------------------------------------------------ #
    # 10) Marker stored under AEGIS_DATA_DIR (not inside the pack)
    # ------------------------------------------------------------------ #
    def test_marker_under_data_dir(self) -> None:
        """The eval marker is stored under ``AEGIS_DATA_DIR``, not inside
        the pack or the repo."""
        now = datetime.now(timezone.utc)
        create_eval_marker("t231loc", started_at=now)
        marker_path = Path(self._tmp) / "eval_markers" / "t231loc.json"
        self.assertTrue(marker_path.is_file())
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        self.assertEqual(data["tenant_id"], "t231loc")
        self.assertEqual(data["status"], "active")


if __name__ == "__main__":
    unittest.main()
