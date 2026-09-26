"""T213 — README Now proven local persons only.

Covers:

* ``test_readme_now_has_one_week_or_morning_night_cold`` — the README Now
  section contains "one week" or "morning" and "night" and "cold".
* ``test_readme_now_does_not_claim_two_week`` — the README does not contain
  "two-week" as a shipped-use claim (bare "two-week" anywhere in Now is a
  fail unless clearly "not two-week").
* ``test_readme_does_not_claim_behavioral_twin`` — the README does not
  contain "behavioral twin" as a shipped claim.
* ``test_readme_now_mentions_amin_or_sara_novak`` — the README Now section
  mentions amin or Sara Novak as a separate account.
* ``test_readme_now_mentions_ricardo`` — the README Now section mentions
  Ricardo as a separate Mac person.
* ``test_readme_does_not_claim_notarized`` — the README does not claim
  notarized.
* ``test_core_has_no_stripe`` — core/ has no stripe token.
* ``test_status_has_t213_line`` — STATUS.md has a T213 line.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_STATUS = _REPO_ROOT / "STATUS.md"

_NT = "not" + "arized"
_BT = "behavioral" + " twin"


class TestT213ReadmeNow(unittest.TestCase):
    """T213 — README Now proven owner amin Ricardo separate days."""

    def setUp(self) -> None:
        self._text = _README.read_text(encoding="utf-8")
        self._rl = self._text.lower()
        self._now_idx = self._text.find("## Now")
        self._planned_idx = self._text.find("## Destination")
        self._now = self._text[self._now_idx : self._planned_idx].lower()

    def test_readme_now_has_one_week_or_morning_night_cold(self) -> None:
        """README Now contains 'one week' or 'morning' and 'night' and 'cold'."""
        self.assertGreater(self._now_idx, 0)
        self.assertGreater(self._planned_idx, self._now_idx)
        cond = (
            "one week" in self._now
            or ("morning" in self._now and "night" in self._now and "cold" in self._now)
        )
        self.assertTrue(cond, "Now must contain one week or morning+night+cold")

    def test_readme_now_does_not_claim_two_week(self) -> None:
        """README does not contain 'two-week' as a shipped-use claim."""
        self.assertNotIn("two-week", self._now)

    def test_readme_does_not_claim_behavioral_twin(self) -> None:
        """README does not contain 'behavioral twin' as a shipped claim."""
        self.assertNotIn(_BT, self._rl)

    def test_readme_now_mentions_amin_or_sara_novak(self) -> None:
        """README Now mentions amin or Sara Novak as a separate account."""
        cond = "amin" in self._now or "sara novak" in self._now
        self.assertTrue(cond, "Now must mention amin or Sara Novak")

    def test_readme_now_mentions_ricardo(self) -> None:
        """README Now mentions Ricardo as a separate Mac person."""
        self.assertIn("ricardo", self._now)

    def test_readme_does_not_claim_notarized(self) -> None:
        """README does not claim notarized."""
        self.assertNotIn(_NT, self._rl)

    def test_core_has_no_stripe(self) -> None:
        """core/ has no stripe token."""
        for py in (_REPO_ROOT / "core").glob("*.py"):
            text = py.read_text(encoding="utf-8")
            self.assertNotIn("stripe", text.lower())

    def test_status_has_t213_line(self) -> None:
        """STATUS.md has a T213 line."""
        self.assertIn("T213", _STATUS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
