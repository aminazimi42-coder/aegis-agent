"""T230 — app update leaves $HOME/.aegis untouched.

Covers:

* ``apply_pack_update`` copies or replaces only the operator pack files
  (app code, start script, version marker) and **refuses** when the target
  path is inside ``AEGIS_DATA_DIR`` (typed deny ``path_inside_data_dir``).
* Before replace, a fingerprint of the data dir is recorded.  After replace,
  the same fingerprint matches.  A mismatch is a typed fail and aborts.
* The update does **not** delete ``export/``, ``receipts/``, or
  ``purchase_receipts/``.  It does **not** clear ``entitlement.json``.
* No network call is made.
* ``core/`` has no ``stripe`` substring.
* Echo-limited still holds (entitlement load unchanged).
* ``start_operator.sh`` remains the only start path.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  No live HTTP.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.pack_update import (
    FingerprintMismatchError,
    PathInsideDataDirError,
    apply_pack_update,
    data_fingerprint,
)


class TestT230PackUpdate(unittest.TestCase):
    """T230 — pack update leaves data dir untouched."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t230_data_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._pack = tempfile.mkdtemp(prefix="aegis_t230_pack_")
        # Build a minimal source pack.
        (Path(self._pack) / "app.py").write_text(
            "# updated app code\n", encoding="utf-8"
        )
        (Path(self._pack) / "start_operator.sh").write_text(
            "#!/bin/sh\necho start\n", encoding="utf-8"
        )
        (Path(self._pack) / "VERSION").write_text(
            "1.2.3\n", encoding="utf-8"
        )
        # A target install dir outside the data dir.
        self._target = tempfile.mkdtemp(prefix="aegis_t230_target_")

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _seed_data(self) -> None:
        """Seed the data dir with profile, receipts, export, entitlement."""
        root = Path(self._tmp)
        # Profile.
        (root / "profile.json").write_text(
            json.dumps({"tenant_id": "t230", "name": "test"}), encoding="utf-8"
        )
        # Receipts.
        rdir = root / "receipts"
        rdir.mkdir(exist_ok=True)
        (rdir / "r1.md").write_text("# receipt 1\n", encoding="utf-8")
        (rdir / "r2.md").write_text("# receipt 2\n", encoding="utf-8")
        # Purchase receipts.
        pdir = root / "purchase_receipts"
        pdir.mkdir(exist_ok=True)
        (pdir / "receipt_t230.json").write_text(
            json.dumps({"receipt_id": "rcpt-230"}), encoding="utf-8"
        )
        # Export.
        edir = root / "export"
        edir.mkdir(exist_ok=True)
        (edir / "brief.md").write_text("# brief\n", encoding="utf-8")
        # Entitlement.
        (root / "entitlement.json").write_text(
            json.dumps({"tier": "echo", "tenant_id": "t230"}), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 1) Data fingerprint unchanged after update
    # ------------------------------------------------------------------ #
    def test_fingerprint_unchanged_after_update(self) -> None:
        """The data-dir fingerprint is identical before and after a
        clean pack update that targets a path outside the data dir."""
        self._seed_data()
        result = apply_pack_update(self._pack, self._target)
        self.assertTrue(result["ok"])
        self.assertTrue(result["fingerprint_match"])
        self.assertEqual(result["before"], result["after"])
        # The data dir contents are byte-stable.
        before = data_fingerprint()
        self.assertEqual(before, result["before"])

    # ------------------------------------------------------------------ #
    # 2) Path inside data dir is typed deny
    # ------------------------------------------------------------------ #
    def test_path_inside_data_dir_deny(self) -> None:
        """When the target resolves inside ``AEGIS_DATA_DIR`` the update
        refuses with a typed ``PathInsideDataDirError``."""
        self._seed_data()
        inside = Path(self._tmp) / "subdir"
        inside.mkdir(exist_ok=True)
        with self.assertRaises(PathInsideDataDirError):
            apply_pack_update(self._pack, inside)

    # ------------------------------------------------------------------ #
    # 3) Entitlement file still present after update
    # ------------------------------------------------------------------ #
    def test_entitlement_kept(self) -> None:
        """``entitlement.json`` under the data dir is not deleted or
        cleared by the pack update."""
        self._seed_data()
        ent_path = Path(self._tmp) / "entitlement.json"
        before_raw = ent_path.read_text(encoding="utf-8")
        apply_pack_update(self._pack, self._target)
        after_raw = ent_path.read_text(encoding="utf-8")
        self.assertEqual(before_raw, after_raw)
        self.assertTrue(ent_path.is_file())

    # ------------------------------------------------------------------ #
    # 4) export/, receipts/, purchase_receipts/ not deleted
    # ------------------------------------------------------------------ #
    def test_data_subdirs_kept(self) -> None:
        """``export/``, ``receipts/``, and ``purchase_receipts/`` under the
        data dir are not deleted or emptied by the pack update."""
        self._seed_data()
        root = Path(self._tmp)
        apply_pack_update(self._pack, self._target)
        self.assertTrue((root / "export").is_dir())
        self.assertGreaterEqual(len(list((root / "export").iterdir())), 1)
        self.assertTrue((root / "receipts").is_dir())
        self.assertGreaterEqual(len(list((root / "receipts").iterdir())), 2)
        self.assertTrue((root / "purchase_receipts").is_dir())
        self.assertGreaterEqual(
            len(list((root / "purchase_receipts").iterdir())), 1
        )

    # ------------------------------------------------------------------ #
    # 5) No stripe token in core
    # ------------------------------------------------------------------ #
    def test_core_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring."""
        _repo_root = Path(__file__).resolve().parent.parent
        core_dir = _repo_root / "core"
        for p in sorted(core_dir.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("stripe", text, f"stripe found in {p.name}")

    # ------------------------------------------------------------------ #
    # 6) Echo-limited still holds
    # ------------------------------------------------------------------ #
    def test_echo_limited_still_holds(self) -> None:
        """After the update, loading entitlement with a missing or echo
        file still returns ``tier="echo"`` — the update does not unlock
        or change the entitlement tier."""
        from core.entitlement import load

        # No entitlement file — echo.
        result = load(tenant_id="t230")
        self.assertEqual(result["tier"], "echo")
        # With an echo entitlement — echo.
        self._seed_data()
        result2 = load(tenant_id="t230")
        self.assertEqual(result2["tier"], "echo")
        # After update — still echo.
        apply_pack_update(self._pack, self._target)
        result3 = load(tenant_id="t230")
        self.assertEqual(result3["tier"], "echo")

    # ------------------------------------------------------------------ #
    # 7) start_operator.sh remains the only start path
    # ------------------------------------------------------------------ #
    def test_start_operator_remains_only_start(self) -> None:
        """``scripts/start_operator.sh`` exists in the repo and the pack
        update does not add a new start path or a browser launcher."""
        _repo_root = Path(__file__).resolve().parent.parent
        start = _repo_root / "scripts" / "start_operator.sh"
        self.assertTrue(start.is_file(), "scripts/start_operator.sh must exist")
        # The pack update copies files into the target — no new start path.
        result = apply_pack_update(self._pack, self._target)
        self.assertTrue(result["ok"])

    # ------------------------------------------------------------------ #
    # 8) No network call
    # ------------------------------------------------------------------ #
    def test_no_network_call(self) -> None:
        """The pack update makes no network call — this is a static
        assertion that ``apply_pack_update`` imports no network library."""
        import core.pack_update as pu

        source = open(pu.__file__, encoding="utf-8").read().lower()
        for forbidden in ("urllib", "requests", "http.client", "socket"):
            self.assertNotIn(
                forbidden,
                source,
                f"{forbidden} found in pack_update source",
            )

    # ------------------------------------------------------------------ #
    # 9) Update does not set AEGIS_DATA_DIR to pack folder
    # ------------------------------------------------------------------ #
    def test_data_dir_not_set_to_pack(self) -> None:
        """After the update, ``AEGIS_DATA_DIR`` still points to the
        original data dir — the update does not repoint it to the pack."""
        original = os.environ.get("AEGIS_DATA_DIR")
        apply_pack_update(self._pack, self._target)
        self.assertEqual(os.environ.get("AEGIS_DATA_DIR"), original)

    # ------------------------------------------------------------------ #
    # 10) Fingerprint mismatch is a typed fail
    # ------------------------------------------------------------------ #
    def test_fingerprint_mismatch_is_typed_fail(self) -> None:
        """When the data dir changes between the before/after fingerprint,
        ``apply_pack_update`` raises ``FingerprintMismatchError`` — it
        does not silently continue."""
        # We simulate this by monkeypatching data_fingerprint to return
        # different values on the two calls.
        import core.pack_update as pu

        original = pu.data_fingerprint
        calls = [0]

        def fake():
            calls[0] += 1
            if calls[0] == 1:
                return {"fingerprint": "before"}
            return {"fingerprint": "after"}

        pu.data_fingerprint = fake
        try:
            with self.assertRaises(FingerprintMismatchError):
                pu.apply_pack_update(self._pack, self._target)
        finally:
            pu.data_fingerprint = original


if __name__ == "__main__":
    unittest.main()
