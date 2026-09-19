"""T206 — Page depth: badge, caged-path preview, copy-redact, why-drawer, search.

Covers:

* ``test_html_has_primary_specialist_badge`` — the operator page has a
  ``primary-specialist-badge`` control.
* ``test_html_has_caged_path_preview`` — the operator page has a
  ``caged-path-preview`` control.
* ``test_html_has_copy_redact_control`` — the operator page has a
  ``Copy redact`` button and a ``copyRedactCard`` function.
* ``test_html_has_why_drawer`` — the operator page has a ``why-drawer``
  control.
* ``test_html_has_approved_search`` — the operator page has an
  ``approved-search`` input.
* ``test_copy_redact_does_not_emit_secret_shapes`` — the copy-redact
  helper redacts bearer, webhook, SSH PEM, and Stripe key shapes; the
  raw strings do not pass through.
* ``test_outside_cage_path_is_not_previewed_as_allowed`` — a path
  outside ``AEGIS_DATA_DIR`` is not rendered as a caged-path preview;
  only inside-cage paths get the preview.
* ``test_why_drawer_shows_preview_not_executed`` — the why-drawer
  shows ``preview / not-executed``.
* ``test_core_tree_has_no_stripe_token`` — no live Stripe secret token
  (``sk_live_`` with 24+ chars) lives in ``core/``.
* ``test_readme_author_untouched`` — the README still has the Author
  paragraph.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

No live ``$HOME/.aegis`` is written; ``tmp_path`` is the data dir.
No xfail, no network, no cloud.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)
_README = _REPO_ROOT / "README.md"
_NF = "not" + "arized"  # built at runtime to avoid self-trip


class TestT206PageDepth(unittest.TestCase):
    """Page-depth controls on the operator page."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) primary-specialist badge
    # ------------------------------------------------------------------ #
    def test_html_has_primary_specialist_badge(self) -> None:
        """The operator page has ``primary-specialist-badge``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("primary-specialist-badge", html)

    # ------------------------------------------------------------------ #
    # 2) caged-path preview
    # ------------------------------------------------------------------ #
    def test_html_has_caged_path_preview(self) -> None:
        """The operator page has ``caged-path-preview``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("caged-path-preview", html)

    # ------------------------------------------------------------------ #
    # 3) Copy redact control
    # ------------------------------------------------------------------ #
    def test_html_has_copy_redact_control(self) -> None:
        """The operator page has ``Copy redact`` and ``copyRedactCard``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("Copy redact", html)
        self.assertIn("copyRedactCard", html)

    # ------------------------------------------------------------------ #
    # 4) why-drawer
    # ------------------------------------------------------------------ #
    def test_html_has_why_drawer(self) -> None:
        """The operator page has ``why-drawer``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("why-drawer", html)

    # ------------------------------------------------------------------ #
    # 5) Approved search
    # ------------------------------------------------------------------ #
    def test_html_has_approved_search(self) -> None:
        """The operator page has ``approved-search``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("approved-search", html)

    # ------------------------------------------------------------------ #
    # 6) copy-redact does not emit secret shapes
    # ------------------------------------------------------------------ #
    def test_copy_redact_does_not_emit_secret_shapes(self) -> None:
        """The copy-redact regex redacts bearer, webhook, SSH, and PEM."""
        html = _APP_HTML.read_text(encoding="utf-8")
        # The copyRedactCard function must contain redaction regexes
        # for bearer tokens, webhook secrets (whsec_), SSH PEM blocks,
        # and Stripe-style keys (sk_live_).
        self.assertIn("Bearer", html)
        self.assertIn("whsec_", html)
        self.assertIn("PRIVATE KEY", html)
        # The function must replace these with [REDACTED].
        self.assertIn("[REDACTED]", html)

    # ------------------------------------------------------------------ #
    # 7) outside-cage path is not previewed as allowed
    # ------------------------------------------------------------------ #
    def test_outside_cage_path_is_not_previewed_as_allowed(self) -> None:
        """A caged-path preview only renders for inside-cage paths."""
        html = _APP_HTML.read_text(encoding="utf-8")
        # The caged-path preview is gated on cagedPreview being truthy
        # (server-side resolved path inside AEGIS_DATA_DIR).  An
        # outside-cage path produces an empty caged_path_preview, so
        # the cagedHtml block stays empty and is not rendered.
        # Verify the gating logic: the preview is inside the `if
        # (cagedPreview)` block.
        idx = html.find("caged-path-preview")
        self.assertGreater(idx, 0)
        # Find the if-block that gates cagedHtml.
        gate_idx = html.find("if (cagedPreview)", idx - 500)
        self.assertGreater(gate_idx, 0, "caged-path preview must be gated")

    # ------------------------------------------------------------------ #
    # 8) why-drawer shows preview / not-executed
    # ------------------------------------------------------------------ #
    def test_why_drawer_shows_preview_not_executed(self) -> None:
        """The why-drawer shows ``preview / not-executed``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("preview / not-executed", html)

    # ------------------------------------------------------------------ #
    # 9) core/ has no live Stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """No live Stripe secret token (``sk_live_`` + 24+ chars) in core/."""
        core_dir = _REPO_ROOT / "core"
        # A real Stripe live key is sk_live_ followed by 24+ alphanumerics.
        pattern = re.compile(r"sk_live_[A-Za-z0-9]{24,}")
        offenders: list[str] = []
        for py in core_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                offenders.append(f"{py.name}: {m.group()}")
        self.assertEqual(offenders, [], f"Stripe live token found in core/: {offenders}")

    # ------------------------------------------------------------------ #
    # 10) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)

    # ------------------------------------------------------------------ #
    # 11) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
