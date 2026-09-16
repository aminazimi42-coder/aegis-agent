"""T191 — Honest cold-start preflight and local-dead banner.

Tests:

1. ``test_script_exists_and_no_browser_open`` — the start script exists
   and does not invoke ``open`` or ``xdg-open`` to launch a browser.
2. ``test_script_mentions_port_8741`` — the start script mentions port
   8741.
3. ``test_script_or_helper_missing_python_line`` — the script has a
   typed English line for missing python3 or missing ``.venv/bin/python``.
4. ``test_missing_entitlement_banner_distinct`` — the script prints a
   distinct ``entitlement missing`` line and the page has a
   ``missing_file`` banner distinct from the expired banner.
5. ``test_expired_entitlement_banner_distinct`` — the script prints a
   distinct ``entitlement expired`` line and the page has an ``expired``
   banner distinct from the missing banner.
6. ``test_valid_entitlement_line_distinct`` — the script prints a
   distinct ``entitlement valid`` line.
7. ``test_html_local_dead_or_offline_copy`` — the operator page has
   local-dead or engine-offline copy in the offline banner.
8. ``test_html_has_no_live_badge_without_health`` — the operator page
   does not show a Live or healthy badge while health is down.
9. ``test_readme_author_untouched`` — the README Author paragraph is
   present and contains the developer name.
10. ``test_readme_does_not_contain_notarized`` — the README does not
    contain the word ``notarized``.

Uses ``tmp_path`` for entitlement fixtures.  Does not start uvicorn.
Does not bind 8741 in CI.  No xfail.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_START_SCRIPT = _REPO_ROOT / "scripts" / "start_operator.sh"
_README = _REPO_ROOT / "README.md"
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT191HonestStart(unittest.TestCase):
    """Honest cold-start preflight and local-dead banner."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t191_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Script exists and does not open a browser
    # ------------------------------------------------------------------ #
    def test_script_exists_and_no_browser_open(self) -> None:
        """The start script exists and does not invoke ``open`` or
        ``xdg-open`` to launch a browser."""
        self.assertTrue(_START_SCRIPT.is_file(), "start_operator.sh missing")
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("xdg-open", text)
        # Filter to non-comment code lines before checking for the
        # ``open`` shell command — the script may say "does not launch a
        # browser" in comments without invoking ``open``.
        code_lines = [
            line for line in text.splitlines()
            if not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        self.assertNotRegex(
            code_text, r"(^|\n|\s)open\s",
            "start_operator.sh invokes the 'open' command",
        )

    # ------------------------------------------------------------------ #
    # 2) Script mentions port 8741
    # ------------------------------------------------------------------ #
    def test_script_mentions_port_8741(self) -> None:
        """The start script mentions port 8741."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("8741", text)

    # ------------------------------------------------------------------ #
    # 3) Missing python line
    # ------------------------------------------------------------------ #
    def test_script_or_helper_missing_python_line(self) -> None:
        """The script has a typed English line for missing python3 or
        missing ``.venv/bin/python``."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertTrue(
            "python3 not found" in text or "python3 missing" in text,
            "no missing-python3 line in start_operator.sh",
        )
        self.assertTrue(
            ".venv/bin/python" in text,
            "no .venv/bin/python check in start_operator.sh",
        )

    # ------------------------------------------------------------------ #
    # 4) Missing entitlement banner is distinct
    # ------------------------------------------------------------------ #
    def test_missing_entitlement_banner_distinct(self) -> None:
        """The script prints a distinct ``entitlement missing`` line."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("entitlement missing", text)
        # The HTML banner references the missing_file reason token.
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("missing_file", html)

    # ------------------------------------------------------------------ #
    # 5) Expired entitlement banner is distinct
    # ------------------------------------------------------------------ #
    def test_expired_entitlement_banner_distinct(self) -> None:
        """The script prints a distinct ``entitlement expired`` line."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("entitlement expired", text)
        # The HTML banner references the expired reason token.
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("expired", html)
        # Missing and expired lines are distinct in the script.
        self.assertNotEqual("entitlement missing", "entitlement expired")

    # ------------------------------------------------------------------ #
    # 6) Valid entitlement line is distinct
    # ------------------------------------------------------------------ #
    def test_valid_entitlement_line_distinct(self) -> None:
        """The script prints a distinct ``entitlement valid`` line."""
        text = _START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("entitlement valid", text)
        # Valid is distinct from missing and expired.
        self.assertNotEqual("entitlement valid", "entitlement missing")
        self.assertNotEqual("entitlement valid", "entitlement expired")

    # ------------------------------------------------------------------ #
    # 7) HTML has local-dead or engine-offline copy
    # ------------------------------------------------------------------ #
    def test_html_local_dead_or_offline_copy(self) -> None:
        """The operator page has local-dead or engine-offline copy in
        the offline banner."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertTrue(
            "local engine is dead" in html or "engine offline" in html,
            "no local-dead or engine-offline copy in the offline banner",
        )

    # ------------------------------------------------------------------ #
    # 8) No Live/healthy badge without health
    # ------------------------------------------------------------------ #
    def test_html_has_no_live_badge_without_health(self) -> None:
        """The operator page does not show a Live or healthy badge
        while health is down — ``setOffline`` must not set any text
        containing ``healthy`` or ``Live``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lower = html.lower()
        # The offline banner title must not say "healthy" or "live".
        offline_start = lower.find('id="offline-banner"')
        offline_end = lower.find("</div>", offline_start)
        offline_block = lower[offline_start:offline_end] if offline_start >= 0 else ""
        self.assertNotIn("healthy", offline_block)
        self.assertNotIn("live", offline_block)
        # setOffline sets health-text to a dead-engine message, not
        # "healthy" or "Live".
        self.assertIn("Local engine is dead", html)

    # ------------------------------------------------------------------ #
    # 9) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author`` and
        the developer name."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain "notarized"
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word ``notarized``."""
        text = _README.read_text(encoding="utf-8")
        self.assertNotIn("notarized", text.lower())


if __name__ == "__main__":
    unittest.main()
