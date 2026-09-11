"""T148 — Pack ships entitlement example only.

Covers:

* ``test_pack_includes_entitlement_example`` — after running the pack
  script, ``dist/aegis-local-operator/entitlement.example.json`` is a
  file with dummy fields (``tenant_id``, ``tier``, ``expires_at``,
  ``signature_sha256``) and obviously fake values.
* ``test_pack_omits_live_aegis_dir_and_directive`` — the packed tree
  contains no ``.aegis`` directory, no ``_directive.txt``, and no
  ``task_instruction.txt``.
* ``test_example_is_not_loaded_as_live_entitlement`` — the example file
  in the pack is not loaded as a live entitlement; ``load()`` reads
  only ``AEGIS_DATA_DIR/entitlement.json`` and returns ``echo`` with
  ``reason="missing_file"`` when that path is absent, even if the
  example sits next to the engine.

No uvicorn subprocess.  No live network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_SCRIPT = REPO_ROOT / "scripts" / "pack_local_operator.sh"


class TestT148PackEntitlementExample(unittest.TestCase):
    """Pack ships entitlement.example.json only — no live entitlement."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t148_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(
            REPO_ROOT / "dist" / "aegis-local-operator",
            ignore_errors=True,
        )

    # ------------------------------------------------------------------ #
    # helper: run the pack once and return the output folder path
    # ------------------------------------------------------------------ #
    def _run_pack(self) -> Path:
        env = dict(os.environ)
        env["AEGIS_DATA_DIR"] = self._tmp
        result = subprocess.run(
            ["/bin/sh", str(PACK_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"pack_local_operator.sh failed: {result.stderr or result.stdout}",
        )
        out_path = result.stdout.strip().splitlines()[-1].strip()
        self.assertTrue(out_path, "pack script printed no output path")
        return Path(out_path)

    # ------------------------------------------------------------------ #
    # 1) Pack includes entitlement.example.json with dummy fields
    # ------------------------------------------------------------------ #
    def test_pack_includes_entitlement_example(self) -> None:
        """The packed folder contains entitlement.example.json with
        dummy fields and obviously fake values."""
        out = self._run_pack()
        example = out / "entitlement.example.json"
        self.assertTrue(
            example.is_file(),
            "pack must include entitlement.example.json",
        )
        data = json.loads(example.read_text(encoding="utf-8"))
        # Must have the four dummy fields.
        for field in (
            "tenant_id",
            "tier",
            "expires_at",
            "signature_sha256",
        ):
            self.assertIn(
                field, data, f"example missing field {field!r}"
            )
        # Values must be obviously fake.
        self.assertEqual(data["tier"], "echo")
        self.assertEqual(data["tenant_id"], "example-tenant")
        self.assertIn(
            "0",
            data["signature_sha256"],
            "example signature must be an obviously fake all-zero hex",
        )

    # ------------------------------------------------------------------ #
    # 2) Pack omits live .aegis dir, _directive.txt, task_instruction.txt
    # ------------------------------------------------------------------ #
    def test_pack_omits_live_aegis_dir_and_directive(self) -> None:
        """The packed tree has no .aegis directory, no _directive.txt,
        and no task_instruction.txt."""
        out = self._run_pack()
        self.assertFalse(
            (out / ".aegis").exists(),
            "pack must not include a live .aegis directory",
        )
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "pack must not include _directive.txt",
        )
        self.assertFalse(
            (out / "task_instruction.txt").exists(),
            "pack must not include task_instruction.txt",
        )

    # ------------------------------------------------------------------ #
    # 3) Example is not loaded as a live entitlement
    # ------------------------------------------------------------------ #
    def test_example_is_not_loaded_as_live_entitlement(self) -> None:
        """The engine loads entitlement only from
        AEGIS_DATA_DIR/entitlement.json, never from the example file in
        the pack.  With no entitlement.json in the data dir, load()
        returns echo / missing_file — even if the example file exists
        in the packed folder."""
        from core.entitlement import ECHO_TIER, load

        # Ensure no live entitlement.json exists in the data dir.
        live = Path(self._tmp) / "entitlement.json"
        self.assertFalse(live.exists(), "test setup must start clean")

        result = load(tenant_id="example-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "missing_file")

        # Run the pack so the example file physically exists on disk;
        # the engine must still not load it.
        out = self._run_pack()
        self.assertTrue(
            (out / "entitlement.example.json").is_file(),
            "pack must have created the example file",
        )
        # The live path is still absent.
        self.assertFalse(live.exists())
        result2 = load(tenant_id="example-tenant")
        self.assertEqual(result2["tier"], ECHO_TIER)
        self.assertEqual(result2["reason"], "missing_file")


if __name__ == "__main__":
    unittest.main()
