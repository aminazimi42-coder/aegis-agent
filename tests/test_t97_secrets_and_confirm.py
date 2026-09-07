"""T97 — secret-shape redaction and L2/L3 typed confirm.

Verifies:

* ``redact_secrets`` redacts JWT-shaped tokens and ``Bearer sk-…`` prefixed
  values in addition to the named env-var keys.
* ``execute`` for an L3 action without the ``CONFIRM`` argument writes
  nothing and exits ``2``.
* ``execute`` for an L3 action with ``CONFIRM`` allowed path succeeds when
  the action is approved and the digest matches.

No live network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _run_aegis(*args: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run ``python -m core.twin_local <args>``; return (code, stdout, stderr)."""
    cmd = [sys.executable, "-m", "core.twin_local", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _write_profile(
    data_dir: str,
    tenant_id: str,
    role: str,
    goal: str,
    consented: bool = True,
) -> Path:
    """Write a consented (or not) profile.json under data_dir/<tenant>/."""
    profile_dir = Path(data_dir) / tenant_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        json.dumps(
            {"role": role, "goal": goal, "consented": consented},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return profile_path


class TestT97SecretsAndConfirm(unittest.TestCase):
    """Secret-shape redaction and L2/L3 typed confirm."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t97_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) redact_secrets — JWT and bearer shapes
    # ------------------------------------------------------------------ #

    def test_redacts_jwt_and_bearer(self) -> None:
        """redact_secrets replaces JWT-shaped tokens and Bearer sk- prefixes."""
        from core.llm_safety import redact_secrets

        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.Sig1234567890"
        bearer = "Bearer sk-test1234567890abcdef"
        aws = "AKIAIOSFODNN7EXAMPLE"

        text = f"keys: {jwt} and {bearer} and {aws}"
        redacted = redact_secrets(text)

        self.assertNotIn(jwt, redacted)
        self.assertNotIn(bearer, redacted)
        self.assertNotIn(aws, redacted)
        self.assertIn("***", redacted)

    # ------------------------------------------------------------------ #
    # 2) L3 execute without CONFIRM writes nothing, exits 2
    # ------------------------------------------------------------------ #

    def test_l3_without_confirm_writes_nothing(self) -> None:
        """execute for an L3 action without CONFIRM exits 2, writes nothing."""
        tenant = "t97_l3_noconfirm"
        _write_profile(self._tmp, tenant, role="architect", goal="deploy production")

        # Propose an action whose title contains an L3 keyword ("deploy").
        code, stdout, stderr = _run_aegis("propose", tenant, env=self._env)
        self.assertEqual(code, 0, f"propose failed: {stderr!r}")

        from core.twin_actions import _load_action, approve, list_actions

        actions = list_actions(tenant)
        pending = [a for a in actions if a.get("status") == "proposed"]
        self.assertGreaterEqual(len(pending), 1)
        action = pending[0]
        action_id = action["action_id"]
        digest = action.get("payload_sha256") or ""

        # Approve so the action is executable.
        approve(action_id, tenant, "actor-t97", expected_payload_sha256=digest)

        # Attempt execute WITHOUT the CONFIRM argument — must exit 2.
        code, stdout, stderr = _run_aegis(
            "execute", action_id, tenant, env=self._env,
        )
        self.assertEqual(code, 2, f"expected exit 2, got {code}: {stderr!r}")

        # Status must still be ``approved`` (not executed).
        reloaded = _load_action(action_id)
        assert reloaded is not None
        self.assertEqual(reloaded["status"], "approved")

        # No receipt file on disk.
        receipt_path = (
            Path(self._tmp) / "work_products" / tenant / "receipts" / f"{action_id}.md"
        )
        self.assertFalse(receipt_path.exists())

    # ------------------------------------------------------------------ #
    # 3) L3 execute with CONFIRM allowed path
    # ------------------------------------------------------------------ #

    def test_l3_with_confirm_allowed_path(self) -> None:
        """execute for an L3 action with CONFIRM succeeds and writes the receipt."""
        tenant = "t97_l3_confirm"
        _write_profile(self._tmp, tenant, role="architect", goal="deploy production")

        # Propose an action whose title contains an L3 keyword ("deploy").
        code, stdout, stderr = _run_aegis("propose", tenant, env=self._env)
        self.assertEqual(code, 0, f"propose failed: {stderr!r}")

        from core.twin_actions import _load_action, approve, list_actions

        actions = list_actions(tenant)
        pending = [a for a in actions if a.get("status") == "proposed"]
        self.assertGreaterEqual(len(pending), 1)
        action = pending[0]
        action_id = action["action_id"]
        digest = action.get("payload_sha256") or ""

        # Approve so the action is executable.
        approve(action_id, tenant, "actor-t97", expected_payload_sha256=digest)

        # Attempt execute WITH the CONFIRM argument — must succeed.
        code, stdout, stderr = _run_aegis(
            "execute", action_id, tenant, "CONFIRM", env=self._env,
        )
        self.assertEqual(code, 0, f"expected exit 0, got {code}: {stderr!r}")
        # T98 — execute now prints a receipt line before the status line.
        self.assertIn("executed", stdout)
        self.assertIn("receipt:", stdout)

        # Status must be ``executed``.
        reloaded = _load_action(action_id)
        assert reloaded is not None
        self.assertEqual(reloaded["status"], "executed")


if __name__ == "__main__":
    unittest.main()
