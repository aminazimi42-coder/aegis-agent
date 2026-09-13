"""T159 — tool-output path cage + no invented profile facts + README smoke.

Tests:
1. A tool write outside ``AEGIS_DATA_DIR`` is rejected with a typed
   English ``ValueError`` and no file is written.
2. A tool write inside ``AEGIS_DATA_DIR`` is allowed and the file
   appears at the expected path.
3. ``propose_profile_fields`` omits fields that are absent from the
   stored profile (no invented name, role, goals, timezone, …).
4. README records the 2026-09-13 hermesdev laptop smoke as a proven
   fact with the required tokens.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_local_view import cage_path


class TestT159ToolPathAndProfile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Path cage — reject writes outside AEGIS_DATA_DIR
    # ------------------------------------------------------------------ #

    def test_tool_write_outside_data_dir_rejected(self) -> None:
        """cage_path rejects a destination that escapes the data root."""
        outside = Path(self._tmp).parent / "escape_target.md"
        with self.assertRaises(ValueError) as ctx:
            cage_path(outside)
        self.assertIn("outside AEGIS_DATA_DIR", str(ctx.exception))
        # No file written.
        self.assertFalse(outside.exists())

    def test_tool_write_inside_data_dir_allowed_shape(self) -> None:
        """cage_path allows a destination inside the data root."""
        inside = Path(self._tmp) / "export" / "local.md"
        resolved = cage_path(inside)
        self.assertEqual(resolved, inside)
        # A relative bare filename should also land inside the root.
        bare = cage_path("bare.md")
        self.assertEqual(bare, Path(self._tmp) / "bare.md")

    # ------------------------------------------------------------------ #
    # 2) No invented profile facts
    # ------------------------------------------------------------------ #

    def test_propose_omits_absent_profile_fields(self) -> None:
        """propose_profile_fields omits fields absent from the profile."""
        from core.agent_base import propose_profile_fields

        # Empty profile → empty dict.
        self.assertEqual(propose_profile_fields(None), {})
        self.assertEqual(propose_profile_fields({}), {})

        # Profile with only one field → only that field.
        profile = {"role": "Operator", "decision_style": "", "tools": None}
        fields = propose_profile_fields(profile)
        self.assertIn("role", fields)
        self.assertNotIn("decision_style", fields)
        self.assertNotIn("tools", fields)
        self.assertNotIn("name", fields)
        self.assertNotIn("goals", fields)
        self.assertNotIn("timezone", fields)

        # A full profile returns only the known fields.
        full = {
            "role": "Operator",
            "decision_style": "data-driven",
            "tools": "python",
            "risk_posture": "cautious",
            "work_ethics": "transparent",
            "repositories": "aegis-agent",
        }
        fields = propose_profile_fields(full)
        self.assertEqual(set(fields.keys()), set(full.keys()))

    # ------------------------------------------------------------------ #
    # 3) README records the 2026-09-13 hermesdev smoke
    # ------------------------------------------------------------------ #

    def test_readme_records_hermesdev_20260913_smoke(self) -> None:
        """README Now contains the proven smoke-fact tokens."""
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("twin-d6587b37304f", readme)
        self.assertIn("122824Z", readme)
        self.assertIn("51c0e5085d82", readme)
        self.assertIn("2026-09-13 hermesdev laptop smoke", readme)


if __name__ == "__main__":
    unittest.main()
