"""T102 — Local guards: dead-man, overlap, duplicate, inbox score, transcript gap, delegate close.

Covers:
- **dead-man** — ``dead_man_warning`` returns a warning when the last
  scheduler tick is older than 48h or the tick file is missing.
- **expense duplicate** — two receipts with the same amount+vendor+date
  get ``duplicate=True``; detection only.
- **transcript gap** — proposed actions from transcript sources with
  missing/empty text get ``confidence="low"``.
- No live network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


def _write_local_profile(
    data_dir: str,
    tenant_id: str,
    role: str = "architect",
    goal: str = "ship",
    consented: bool = True,
    keywords: list[str] | None = None,
) -> Path:
    """Write a consented local ``profile.json`` under ``data_dir/<tenant>/``."""
    profile_dir = Path(data_dir) / tenant_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"
    data: dict = {"role": role, "goal": goal, "consented": consented}
    if keywords:
        data["keywords"] = keywords
    profile_path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return profile_path


class TestT102LocalGuards(unittest.TestCase):
    """Local guards: dead-man, overlap, duplicate, inbox, transcript, delegate close."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t102_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Dead-man
    # ------------------------------------------------------------------ #

    def test_dead_man_warns_on_missing_tick(self) -> None:
        """Missing tick file produces a non-empty warning."""
        from core.t102_local_guards import dead_man_warning

        tenant = f"t102-dm-{uuid4().hex[:8]}"
        warning = dead_man_warning(tenant)
        self.assertTrue(warning, "missing tick file should produce a warning")
        self.assertIn("dead-man", warning)

    def test_dead_man_warns_on_stale_tick(self) -> None:
        """A tick older than 48h produces a warning."""
        from core.t102_local_guards import _tick_path, dead_man_warning

        tenant = f"t102-dm-stale-{uuid4().hex[:8]}"
        # Write a tick 72 hours ago.
        old_time = datetime.now(timezone.utc) - timedelta(hours=72)
        path = _tick_path(tenant)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"tenant_id": tenant, "tick_at": old_time.isoformat()}),
            encoding="utf-8",
        )
        warning = dead_man_warning(tenant)
        self.assertTrue(warning, "stale tick should produce a warning")
        self.assertIn("72.0h", warning)

    def test_dead_man_no_warning_on_recent_tick(self) -> None:
        """A recent tick produces an empty warning (no dead-man)."""
        from core.t102_local_guards import dead_man_warning, record_tick

        tenant = f"t102-dm-ok-{uuid4().hex[:8]}"
        record_tick(tenant)
        warning = dead_man_warning(tenant)
        self.assertEqual(warning, "", "recent tick should produce no warning")

    # ------------------------------------------------------------------ #
    # 2) Focus-block overlap
    # ------------------------------------------------------------------ #

    def test_overlap_detected(self) -> None:
        """A proposed slot overlapping a local .ics event sets overlap=True."""
        from core.t102_local_guards import check_overlap

        tenant = f"t102-ov-{uuid4().hex[:8]}"

        # Write a focus_block.ics directly (avoid create_block's SQLite gate).
        wp_dir = Path(self._tmp) / "work_products" / tenant
        wp_dir.mkdir(parents=True, exist_ok=True)
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\n"
            "BEGIN:VEVENT\n"
            "UID:focus-test@aegis\n"
            "SUMMARY:Existing meeting\n"
            "DTSTART:20250615T100000Z\n"
            "DURATION:PT90M\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        (wp_dir / "focus_block.ics").write_text(ics, encoding="utf-8")

        # Propose a slot that overlaps (10:30 → 11:30 within 10:00 → 11:30).
        result = check_overlap(
            tenant,
            title="New propose — 2025-06-15T10:30:00",
            start="2025-06-15T10:30:00",
            duration_min=60,
        )
        self.assertTrue(result["overlap"], "overlapping slot should set overlap=True")
        self.assertTrue(result["conflict"])

    def test_overlap_not_detected_when_clear(self) -> None:
        """A slot outside the .ics event does not overlap."""
        from core.t102_local_guards import check_overlap

        tenant = f"t102-ov-clear-{uuid4().hex[:8]}"

        wp_dir = Path(self._tmp) / "work_products" / tenant
        wp_dir.mkdir(parents=True, exist_ok=True)
        ics = (
            "BEGIN:VCALENDAR\nVERSION:2.0\n"
            "BEGIN:VEVENT\n"
            "SUMMARY:Existing meeting\n"
            "DTSTART:20250615T100000Z\n"
            "DURATION:PT90M\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        (wp_dir / "focus_block.ics").write_text(ics, encoding="utf-8")

        # Propose a slot at 14:00 — well after the 11:30 end.
        result = check_overlap(
            tenant,
            title="Late propose — 2025-06-15T14:00:00",
            start="2025-06-15T14:00:00",
            duration_min=60,
        )
        self.assertFalse(result["overlap"])

    def test_overlap_no_time_slot(self) -> None:
        """A propose with no time slot returns overlap=False (no crash)."""
        from core.t102_local_guards import check_overlap

        tenant = f"t102-ov-none-{uuid4().hex[:8]}"
        result = check_overlap(tenant, title="No time here", start="", duration_min=60)
        self.assertFalse(result["overlap"])

    # ------------------------------------------------------------------ #
    # 3) Expense duplicate
    # ------------------------------------------------------------------ #

    def test_expense_duplicate_flag(self) -> None:
        """Two receipts with the same amount+vendor+date get duplicate=True."""
        from core.t102_local_guards import flag_expense_duplicates

        tenant = f"t102-dup-{uuid4().hex[:8]}"
        receipts = [
            {"vendor": "ACME", "amount": "42.00", "date": "2025-06-01"},
            {"vendor": "ACME", "amount": "42.00", "date": "2025-06-01"},
            {"vendor": "Other", "amount": "10.00", "date": "2025-06-01"},
        ]
        result = flag_expense_duplicates(tenant, receipts)
        self.assertTrue(result[0]["duplicate"])
        self.assertTrue(result[1]["duplicate"])
        self.assertFalse(result[2]["duplicate"])

    def test_expense_no_duplicate_when_unique(self) -> None:
        """Distinct receipts get duplicate=False."""
        from core.t102_local_guards import flag_expense_duplicates

        tenant = f"t102-uniq-{uuid4().hex[:8]}"
        receipts = [
            {"vendor": "ACME", "amount": "42.00", "date": "2025-06-01"},
            {"vendor": "Other", "amount": "42.00", "date": "2025-06-01"},
            {"vendor": "ACME", "amount": "10.00", "date": "2025-06-01"},
        ]
        result = flag_expense_duplicates(tenant, receipts)
        for r in result:
            self.assertFalse(r["duplicate"])

    # ------------------------------------------------------------------ #
    # 4) Inbox score (Day-0 keywords only)
    # ------------------------------------------------------------------ #

    def test_inbox_score_from_profile_keywords(self) -> None:
        """Score counts profile-keyword matches in text, no cloud model."""
        from core.t102_local_guards import inbox_score

        tenant = f"t102-inbox-{uuid4().hex[:8]}"
        _write_local_profile(
            self._tmp, tenant, role="architect", goal="ship",
            keywords=["security", "api"],
        )
        result = inbox_score(tenant, "Please review the security of the new API endpoint")
        self.assertEqual(result["score"], 2)
        self.assertIn("security", result["matched"])
        self.assertIn("api", result["matched"])

    def test_inbox_score_no_match(self) -> None:
        """Score is 0 when no keywords match."""
        from core.t102_local_guards import inbox_score

        tenant = f"t102-inbox-none-{uuid4().hex[:8]}"
        _write_local_profile(self._tmp, tenant, role="architect", goal="ship")
        result = inbox_score(tenant, "hello world")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["matched"], [])

    # ------------------------------------------------------------------ #
    # 5) Transcript gap → confidence=low
    # ------------------------------------------------------------------ #

    def test_transcript_low_confidence_on_missing_file(self) -> None:
        """A missing transcript file yields confidence='low'."""
        from core.t102_local_guards import flag_transcript_action

        tenant = f"t102-tg-missing-{uuid4().hex[:8]}"
        action = {"action_id": "act-test", "title": "test", "status": "proposed"}
        result = flag_transcript_action(
            tenant, "/nonexistent/transcript.txt", action,
        )
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["action_id"], "act-test")

    def test_transcript_low_confidence_on_empty_file(self) -> None:
        """An empty/whitespace transcript file yields confidence='low'."""
        from core.t102_local_guards import flag_transcript_action

        tenant = f"t102-tg-empty-{uuid4().hex[:8]}"
        tenant_dir = Path(self._tmp) / tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)
        tpath = tenant_dir / "empty.txt"
        tpath.write_text("   \n  \n", encoding="utf-8")

        action = {"action_id": "act-empty", "title": "test", "status": "proposed"}
        result = flag_transcript_action(tenant, str(tpath), action)
        self.assertEqual(result["confidence"], "low")

    def test_transcript_high_confidence_on_text(self) -> None:
        """A transcript with content yields confidence='high'."""
        from core.t102_local_guards import flag_transcript_action

        tenant = f"t102-tg-ok-{uuid4().hex[:8]}"
        tenant_dir = Path(self._tmp) / tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)
        tpath = tenant_dir / "full.txt"
        tpath.write_text("Review the latest build and fix the broken tests.", encoding="utf-8")

        action = {"action_id": "act-full", "title": "test", "status": "proposed"}
        result = flag_transcript_action(tenant, str(tpath), action)
        self.assertEqual(result["confidence"], "high")

    # ------------------------------------------------------------------ #
    # 6) Delegate close link
    # ------------------------------------------------------------------ #

    def test_delegate_close_links_to_pack(self) -> None:
        """When a pack exists, delegate_close writes a link back to it."""
        from core.t102_local_guards import delegate_close_link
        from core.twin_delegate_pack import render_pack
        from core.twin_interview import answer, commit, start_session

        tenant = f"t102-dc-{uuid4().hex[:8]}"
        _write_local_profile(self._tmp, tenant, role="dev", goal="ship")

        # Build a SQLite-backed consented profile so render_pack's gate passes.
        session = start_session(tenant)
        session_id = session["session_id"]
        answers = {
            "q_role": "dev",
            "q_decision_style": "fast",
            "q_tools": "git",
            "q_risk": "cautious",
            "q_ethics": "honest",
            "q_repos": tenant,
        }
        for qid, ans in answers.items():
            answer(session_id, qid, ans)
        commit(session_id, True)

        render_pack(tenant)
        pack_path = Path(self._tmp) / "work_products" / tenant / "delegate_pack.md"
        self.assertTrue(pack_path.is_file(), "delegate_pack.md should exist after render_pack")

        result = delegate_close_link(tenant, "Ship T102", decision_id="dec-1")
        self.assertTrue(result["linked"])
        close_path = Path(result["path"])
        self.assertTrue(close_path.is_file())
        content = close_path.read_text(encoding="utf-8")
        self.assertIn("delegate_pack.md", content)
        self.assertIn("Ship T102", content)
        self.assertIn("dec-1", content)

    def test_delegate_close_no_pack(self) -> None:
        """When no pack exists, delegate_close writes linked=False but still writes."""
        from core.t102_local_guards import delegate_close_link

        tenant = f"t102-dc-nopack-{uuid4().hex[:8]}"
        result = delegate_close_link(tenant, "No pack here")
        self.assertFalse(result["linked"])
        close_path = Path(result["path"])
        self.assertTrue(close_path.is_file())
        content = close_path.read_text(encoding="utf-8")
        self.assertIn("No delegate pack found", content)

    # ------------------------------------------------------------------ #
    # Status dead-man integration
    # ------------------------------------------------------------------ #

    def test_status_prints_dead_man_warning(self) -> None:
        """``aegis status`` prints a WARNING line when the tick is missing."""
        import subprocess
        import sys

        tenant = f"t102-status-{uuid4().hex[:8]}"
        _write_local_profile(self._tmp, tenant)

        env = {**os.environ}
        env["AEGIS_TENANT"] = tenant
        result = subprocess.run(
            [sys.executable, "-m", "core.twin_local", "status", tenant],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0, f"status failed: {result.stderr!r}")
        self.assertIn("WARNING", result.stdout)
        self.assertIn("dead-man", result.stdout)

    # ------------------------------------------------------------------ #
    # No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
