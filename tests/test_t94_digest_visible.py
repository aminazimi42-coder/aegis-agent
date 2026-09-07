"""T94 — CI scan and visible approve digest.

Covers:
- ``aegis propose TENANT_ID`` success output includes ``payload_sha256``
  on its own line (not only inside the JSON blob).
- ``aegis status`` queue section includes the digest for each pending
  item when present.
- No live network.
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


class TestT94DigestVisible(unittest.TestCase):
    """``propose`` prints digest; ``status`` shows pending digest."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t94_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_propose_prints_digest(self) -> None:
        """propose success output includes payload_sha256 on its own line."""
        _write_profile(
            self._tmp,
            "t94_digest",
            role="architect",
            goal="ship the digest",
            consented=True,
        )

        code, stdout, stderr = _run_aegis(
            "propose", "t94_digest", env=self._env,
        )
        self.assertEqual(
            code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}"
        )

        # The JSON blob always contains payload_sha256; the T94 requirement
        # is that it also appears on its own ``payload_sha256: <hex>`` line
        # so ``aegis approve`` can read it without parsing JSON.
        lines = stdout.splitlines()
        digest_lines = [
            ln for ln in lines if ln.startswith("payload_sha256:")
        ]
        self.assertEqual(
            len(digest_lines),
            1,
            f"expected exactly one payload_sha256 line, got {digest_lines!r}",
        )

        # The digest must be a 64-char hex SHA-256.
        digest = digest_lines[0].split("payload_sha256:", 1)[1].strip()
        self.assertEqual(len(digest), 64)
        self.assertTrue(
            all(c in "0123456789abcdef" for c in digest),
            f"digest not hex: {digest!r}",
        )

        # The same digest must appear inside the JSON result.
        json_line = [
            ln for ln in lines if ln.startswith("{") and "payload_sha256" in ln
        ]
        self.assertTrue(json_line, "JSON result line not found")
        parsed = json.loads(json_line[0])
        self.assertEqual(parsed.get("payload_sha256"), digest)

    def test_status_shows_pending_digest(self) -> None:
        """status queue section includes digest for pending items when present."""
        _write_profile(
            self._tmp,
            "t94_status",
            role="engineer",
            goal="review the plan",
            consented=True,
        )

        # Insert one proposed action first.
        code, stdout, stderr = _run_aegis(
            "propose", "t94_status", env=self._env,
        )
        self.assertEqual(
            code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}"
        )
        digest_lines = [
            ln for ln in stdout.splitlines()
            if ln.startswith("payload_sha256:")
        ]
        self.assertEqual(len(digest_lines), 1)
        proposed_digest = digest_lines[0].split("payload_sha256:", 1)[1].strip()

        # Now run ``status`` and check the pending digest appears.
        code, stdout, stderr = _run_aegis(
            "status", "t94_status", env=self._env,
        )
        self.assertEqual(
            code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}"
        )

        self.assertIn("## QUEUE", stdout)
        self.assertIn("pending: 1", stdout)

        # The digest for the pending item must be shown.
        self.assertIn("pending_digest:", stdout)
        self.assertIn(proposed_digest, stdout)


if __name__ == "__main__":
    unittest.main()
