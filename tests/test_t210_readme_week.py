"""T210 — Honest README Now for one-week cold-start use.

Covers:

* ``test_author_paragraph_untouched`` — the README Author paragraph
  is present and intact.
* ``test_readme_has_one_week_cold_start_now`` — the README Now section
  contains a one-week cold-start sentence.
* ``test_readme_does_not_claim_two_week`` — the README does not claim
  a fortnight period.
* ``test_readme_does_not_claim_behavioral_twin`` — the README does not
  use the forbidden twin-phrase.
* ``test_readme_does_not_contain_notarized`` — the README does not
  contain the forbidden app-store word.
* ``test_readme_names_ricardo`` — T213 supersedes T210: the README Now
  names Ricardo as a separate Mac person.
* ``test_status_has_t210_line`` — STATUS.md has a T210 line.
* ``test_core_tree_has_no_stripe_token`` — no ``stripe`` token in any
  ``core/*.py`` file.

Does not write live ``$HOME/.aegis``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_STATUS = _REPO_ROOT / "STATUS.md"

_NT = "not" + "arized"
_RD = "ric" + "hardo"
_BT = "behavioral" + " twin"


class TestT210ReadmeWeek(unittest.TestCase):
    """T210 — one-week cold-start Now sentence and status lock."""

    def test_author_paragraph_untouched(self) -> None:
        """The README Author paragraph is present and intact."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    def test_readme_has_one_week_cold_start_now(self) -> None:
        """The README Now section has a one-week cold-start sentence."""
        text = _README.read_text(encoding="utf-8")
        now_idx = text.find("## Now")
        planned_idx = text.find("## Destination")
        self.assertGreater(now_idx, 0)
        self.assertGreater(planned_idx, now_idx)
        now_section = text[now_idx:planned_idx].lower()
        self.assertTrue(
            "one week" in now_section or "one-week" in now_section,
            "one-week must appear in the Now section",
        )

    def test_readme_does_not_claim_two_week(self) -> None:
        """The README does not claim a fortnight period."""
        rl = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn("two week", rl)
        self.assertNotIn("two-week", rl)

    def test_readme_does_not_claim_behavioral_twin(self) -> None:
        """The README does not use the forbidden twin-phrase."""
        rl = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_BT, rl)

    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the forbidden app-store word."""
        rl = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NT, rl)

    def test_readme_names_ricardo(self) -> None:
        """T213 supersedes T210: the README Now names Ricardo as a
        separate Mac person."""
        rl = _README.read_text(encoding="utf-8").lower()
        self.assertIn("ricardo", rl)

    def test_status_has_t210_line(self) -> None:
        """STATUS.md has a T210 line."""
        text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T210", text)

    def test_core_tree_has_no_stripe_token(self) -> None:
        """No core/*.py file contains the stripe token."""
        import glob

        for py in glob.glob(str(_REPO_ROOT / "core" / "*.py")):
            text = Path(py).read_text(encoding="utf-8")
            self.assertNotIn("stripe", text.lower())


if __name__ == "__main__":
    unittest.main()
