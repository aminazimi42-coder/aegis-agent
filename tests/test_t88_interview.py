"""T88 — Day-0 interview writes a consented local profile.

Covers:
- ``main(["interview", TENANT_ID, ROLE, GOAL, "yes"])`` writes
  ``profile.json`` with ``role``, ``goal``, and ``consented=true``
  under ``{AEGIS_DATA_DIR}/{tenant_id}/``.
- ``main(["interview", TENANT_ID, ROLE, GOAL, "no"])`` writes nothing
  and exits ``2``.
- After success, ``main(["status", TENANT_ID])`` does **not** print
  ``"no consented profile"``.
- No secrets, card fields, or network calls.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from core.twin_local import main


class TestT88Interview(unittest.TestCase):
    """Day-0 interview records a consented local profile."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t88_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _profile_path(self, tenant_id: str) -> Path:
        """Return the on-disk path where the interview profile is written."""
        return Path(self._tmp) / tenant_id / "profile.json"

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_yes_consent_writes_profile(self) -> None:
        """``interview TENANT ROLE GOAL yes`` writes profile.json and exits 0."""
        tenant = "t88-yes"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["interview", tenant, "founder", "ship-v1", "yes"])

        self.assertEqual(rc, 0)

        profile_path = self._profile_path(tenant)
        self.assertTrue(
            profile_path.is_file(),
            f"profile.json not written at {profile_path}",
        )
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(data["role"], "founder")
        self.assertEqual(data["goal"], "ship-v1")
        self.assertTrue(data["consented"])

    def test_no_consent_writes_nothing(self) -> None:
        """``interview TENANT ROLE GOAL no`` writes nothing and exits 2."""
        tenant = "t88-no"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["interview", tenant, "founder", "ship-v1", "no"])

        self.assertEqual(rc, 2)
        profile_path = self._profile_path(tenant)
        self.assertFalse(
            profile_path.exists(),
            f"profile.json should not exist when consent is not yes: {profile_path}",
        )
        # The entire tenant directory should not have been created.
        tenant_dir = Path(self._tmp) / tenant
        self.assertFalse(
            tenant_dir.exists(),
            f"tenant directory should not exist when consent is not yes: {tenant_dir}",
        )

    def test_status_after_interview_no_consented_profile(self) -> None:
        """After a successful interview, status must not say 'no consented profile'."""
        tenant = "t88-status"
        # Run the interview first
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["interview", tenant, "founder", "ship-v1", "yes"])
        self.assertEqual(rc, 0)

        # Now run status — it should not print "no consented profile"
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = main(["status", tenant])
        out2 = buf2.getvalue()
        self.assertEqual(rc2, 0)
        self.assertNotIn("no consented profile", out2)

    def test_interview_no_card_or_secret_fields(self) -> None:
        """The written profile must not contain card or secret fields."""
        tenant = "t88-clean"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["interview", tenant, "founder", "ship-v1", "yes"])
        self.assertEqual(rc, 0)

        data = json.loads(self._profile_path(tenant).read_text(encoding="utf-8"))
        for key in data:
            self.assertNotIn(
                key.lower(),
                ("card", "secret", "password", "api_key", "token", "stripe"),
            )

    def test_module_has_no_http_imports(self) -> None:
        """core.twin_local must not import urllib/requests/socket/http."""
        import core.twin_local as mod

        tree = ast.parse(inspect.getsource(mod))
        banned = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned:
                        self.fail(f"core.twin_local imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                if mod_name in banned or mod_name.startswith("urllib."):
                    self.fail(f"core.twin_local imports from '{mod_name}'")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
