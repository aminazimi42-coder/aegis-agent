"""T209_FIX — operator page JavaScript syntax in copy-redact onclick.

Both operator HTML copies (app.html at the repo root and the copy inside
desktop/macos/Aegis.app/Contents/Resources/) must parse as JavaScript.
The T206 copy-redact onclick had an illegal escaped-string shape that
broke the IIFE; this test verifies the fix stays.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP_HTML = REPO / "app.html"
DESKTOP_HTML = REPO / "desktop" / "macos" / "Aegis.app" / "Contents" / "Resources" / "app.html"

# Two literal backslashes before two single quotes — the broken shape.
BROKEN = r"copyRedactCard(\\''"
# One literal backslash before the quote pair — the fixed shape.
GOOD = r"copyRedactCard(\'' + esc(a.action_id || " + '""' + r") + '\')"


def _extract_script(text):
    m = re.search(r"<script>(.*)</script>", text, re.DOTALL)
    if not m:
        return None
    return m.group(1)


def test_both_html_files_exist():
    assert APP_HTML.is_file(), f"missing {APP_HTML}"
    assert DESKTOP_HTML.is_file(), f"missing {DESKTOP_HTML}"


def test_broken_substring_absent_app_html():
    text = APP_HTML.read_text()
    assert BROKEN not in text, "broken copyRedactCard onclick still in app.html"


def test_broken_substring_absent_desktop_html():
    text = DESKTOP_HTML.read_text()
    assert BROKEN not in text, "broken copyRedactCard onclick still in desktop app.html"


def test_good_onclick_present_app_html():
    text = APP_HTML.read_text()
    assert GOOD in text, "good copyRedactCard onclick missing from app.html"


def test_good_onclick_present_desktop_html():
    text = DESKTOP_HTML.read_text()
    assert GOOD in text, "good copyRedactCard onclick missing from desktop app.html"


def test_scripts_identical():
    s1 = _extract_script(APP_HTML.read_text())
    s2 = _extract_script(DESKTOP_HTML.read_text())
    assert s1 is not None, "no <script> block in app.html"
    assert s2 is not None, "no <script> block in desktop app.html"
    assert s1 == s2, "app.html and desktop app.html scripts differ"


def test_node_check_both_scripts():
    node = shutil.which("node")
    if node is None:
        return  # skip node --check when node is absent
    for p in [APP_HTML, DESKTOP_HTML]:
        script = _extract_script(p.read_text())
        assert script is not None, f"no <script> block in {p}"
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(script)
            tmpjs = f.name
        try:
            result = subprocess.run(
                [node, "--check", tmpjs], capture_output=True, text=True
            )
            assert result.returncode == 0, (
                f"node --check failed for {p.name}: {result.stderr}"
            )
        finally:
            Path(tmpjs).unlink(missing_ok=True)
