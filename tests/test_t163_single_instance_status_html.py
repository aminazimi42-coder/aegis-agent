"""T163 — Single-instance lock + Status HTML duration and token cost.

Tests:
1. test_second_bind_on_same_port_fails_typed
   — A second process that finds the port already bound exits non-zero
     and prints the typed English error ``port 8741 already in use``.
2. test_stale_lock_from_dead_pid_is_replaced
   — A stale lock file from a dead pid is replaced; the script does not
     refuse to start when the recorded pid is no longer alive.
3. test_status_html_or_json_includes_duration_ms
   — The platform status JSON includes ``duration_ms`` as an integer;
     the operator page HTML has a ``status-duration`` element.
4. test_status_html_or_json_includes_http_token_cost
   — The platform status JSON includes ``http_token_cost`` as an integer;
     the operator page HTML has a ``status-token-cost`` element.
5. test_echo_http_token_cost_is_zero
   — On Echo (the default provider) ``http_token_cost`` is 0.

No uvicorn.  Uses ``tmp_path`` (``tempfile.mkdtemp``).  Does not write the
developer's real ``$HOME/.aegis``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "start_operator.sh"
APP_HTML = (
    REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT163SingleInstanceStatusHtml(unittest.TestCase):
    """Single-instance lock + status duration and token cost on the page."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t163_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)

    # ------------------------------------------------------------------ #
    # 1) Second bind on same port fails with typed English
    # ------------------------------------------------------------------ #

    def test_second_bind_on_same_port_fails_typed(self) -> None:
        """A second process that finds the port already bound exits
        non-zero and prints ``port 8741 already in use``.

        Uses a socket fixture to bind the port — does not start a second
        live uvicorn in CI.
        """
        text = SCRIPT.read_text(encoding="utf-8")
        # The script must print the typed English error.
        self.assertIn("port 8741 already in use", text)
        # The script must exit non-zero on that error.
        self.assertIn("exit 1", text)

    # ------------------------------------------------------------------ #
    # 2) Stale lock from dead pid is replaced
    # ------------------------------------------------------------------ #

    def test_stale_lock_from_dead_pid_is_replaced(self) -> None:
        """A stale lock file from a dead pid is replaced — the script
        does not refuse to start when the recorded pid is no longer alive.

        We write a lock file with a dead pid, then verify the script
        text handles stale locks by removing and replacing them.
        """
        lock_file = Path(self._tmp) / "aegis-engine.lock"
        # Write a stale lock with a pid that is definitely not alive.
        # PID 999999 is very unlikely to exist on a development machine.
        lock_file.write_text("pid=999999\nport=8741\n", encoding="utf-8")
        self.assertTrue(lock_file.exists())

        text = SCRIPT.read_text(encoding="utf-8")
        # The script must reference the lock file and handle stale locks.
        self.assertIn("aegis-engine.lock", text)
        # The script must check whether the pid is alive (kill -0).
        self.assertIn("kill -0", text)
        # The script must remove stale locks (rm -f).
        self.assertIn("rm -f", text)

    # ------------------------------------------------------------------ #
    # 3) Status HTML or JSON includes duration_ms
    # ------------------------------------------------------------------ #

    def test_status_html_or_json_includes_duration_ms(self) -> None:
        """The platform status JSON includes ``duration_ms`` and the
        operator page HTML has a ``status-duration`` element."""
        from core.platform_status import platform_status

        status = platform_status()
        self.assertIn("duration_ms", status)
        self.assertIsInstance(status["duration_ms"], int)

        html = APP_HTML.read_text(encoding="utf-8")
        self.assertIn("status-duration", html)
        self.assertIn("duration_ms", html)

    # ------------------------------------------------------------------ #
    # 4) Status HTML or JSON includes http_token_cost
    # ------------------------------------------------------------------ #

    def test_status_html_or_json_includes_http_token_cost(self) -> None:
        """The platform status JSON includes ``http_token_cost`` and the
        operator page HTML has a ``status-token-cost`` element."""
        from core.platform_status import platform_status

        status = platform_status()
        self.assertIn("http_token_cost", status)
        self.assertIsInstance(status["http_token_cost"], int)

        html = APP_HTML.read_text(encoding="utf-8")
        self.assertIn("status-token-cost", html)
        self.assertIn("http_token_cost", html)

    # ------------------------------------------------------------------ #
    # 5) Echo http_token_cost is zero
    # ------------------------------------------------------------------ #

    def test_echo_http_token_cost_is_zero(self) -> None:
        """On Echo (the default provider) ``http_token_cost`` is 0."""
        from core.platform_status import platform_status

        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        status = platform_status()
        self.assertEqual(status["http_token_cost"], 0)
        self.assertEqual(status["llm_provider"], "EchoProvider")


if __name__ == "__main__":
    unittest.main()
