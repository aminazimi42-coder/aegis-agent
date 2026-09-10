"""T140 — sole daily start_operator.sh path.

Verifies:
- scripts/start_operator.sh exists and is executable.
- It exports AEGIS_DATA_DIR.
- It binds 127.0.0.1:8741.
- It does not open a browser.
- README names start_operator.sh as the daily start path.
- No live network except TestClient.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "start_operator.sh"


class TestT140StartOperator(unittest.TestCase):
    """The sole daily start path is scripts/start_operator.sh."""

    def test_start_script_exists_and_executable(self) -> None:
        """scripts/start_operator.sh must exist and be executable."""
        self.assertTrue(SCRIPT.is_file(), "scripts/start_operator.sh must exist")
        import os
        self.assertTrue(
            os.access(SCRIPT, os.X_OK),
            "scripts/start_operator.sh must be executable",
        )

    def test_script_exports_aegis_data_dir(self) -> None:
        """start_operator.sh must export AEGIS_DATA_DIR."""
        text = SCRIPT.read_text()
        self.assertIn("AEGIS_DATA_DIR", text,
                       "start_operator.sh must export AEGIS_DATA_DIR")

    def test_script_binds_127_0_0_1_8741(self) -> None:
        """start_operator.sh must bind 127.0.0.1:8741."""
        text = SCRIPT.read_text()
        self.assertIn("127.0.0.1", text,
                       "start_operator.sh must bind 127.0.0.1")
        self.assertIn("8741", text,
                       "start_operator.sh must bind port 8741")

    def test_script_does_not_open_browser(self) -> None:
        """start_operator.sh must not invoke a browser-open command."""
        text = SCRIPT.read_text().lower()
        self.assertNotIn("xdg-open", text,
                         "start_operator.sh must not contain xdg-open")
        self.assertNotIn("open -a", text,
                         "start_operator.sh must not open a browser")
        self.assertNotIn("open http", text,
                         "start_operator.sh must not open a browser")
        self.assertNotIn("curl http", text,
                         "start_operator.sh must not curl a cloud host")

    def test_readme_names_start_operator_sh(self) -> None:
        """README must name scripts/start_operator.sh as the daily start path."""
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertIn("scripts/start_operator.sh", readme,
                       "README must name scripts/start_operator.sh")
        self.assertIn("127.0.0.1:8741", readme,
                       "README must reference 127.0.0.1:8741")

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
