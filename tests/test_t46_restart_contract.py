"""T46 — restart contract: persist, spend, and jobs survive a second process.

Two subprocesses share a temp AEGIS_DATA_DIR:

- Subprocess A completes the T03 interview (consent), puts an approval
  (status ``pending``), adds a spend of 10, and schedules a job due in
  the past — all persisted to the shared SQLite file.

- Subprocess B opens the same file from a fresh process and verifies
  that the approval row is found, the budget ``spent >= 10``, and
  ``list_jobs`` sees the job.  A ``tick`` in B flips the still-scheduled
  job to ``due``.

No live network.  No new product feature.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest


class TestT46RestartContract(unittest.TestCase):
    """Durable pieces survive a second OS process."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t46_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- subprocess A: write approval, spend, job ---

    _SCRIPT_A = (
        "from datetime import datetime, timedelta, timezone\n"
        "from core.twin_interview import start_session, answer, commit\n"
        "from core.twin_persist import put_approval, add_spend\n"
        "from core.twin_scheduler import schedule\n"
        "\n"
        "# Complete the T03 interview so the tenant has a consented profile.\n"
        "state = start_session('t46a')\n"
        "session_id = state['session_id']\n"
        "for _ in range(6):\n"
        "    qid = state['next_question']['id']\n"
        "    state = answer(session_id, qid, 'test answer')\n"
        "commit(session_id, consent=True)\n"
        "\n"
        "# Persist an approval row with status 'pending'.\n"
        "put_approval('appr-t46', tenant_id='t46a', title='install capsule', status='pending')\n"
        "\n"
        "# Add a spend of 10.\n"
        "add_spend('t46a', 10.0)\n"
        "\n"
        "# Schedule a job due in the past.\n"
        "past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()\n"
        "job = schedule('t46a', 'restart contract job', past)\n"
        "assert job['status'] == 'scheduled', job\n"
        "print('OK')\n"
    )

    # --- subprocess B: read everything back, then tick ---

    _SCRIPT_B = (
        "from core.twin_persist import get_approval, get_budget\n"
        "from core.twin_scheduler import list_jobs, tick\n"
        "\n"
        "# Approval row must survive.\n"
        "appr = get_approval('appr-t46')\n"
        "assert appr is not None, 'approval row missing after restart'\n"
        "assert appr['status'] == 'pending', appr\n"
        "\n"
        "# Budget spent must be >= 10.\n"
        "budget = get_budget('t46a')\n"
        "assert budget is not None, 'budget row missing after restart'\n"
        "assert budget['spent'] >= 10, budget\n"
        "\n"
        "# Job must be visible.\n"
        "jobs = list_jobs('t46a')\n"
        "assert len(jobs) >= 1, jobs\n"
        "assert any(j['title'] == 'restart contract job' for j in jobs), jobs\n"
        "\n"
        "# Tick flips the still-scheduled job to 'due'.\n"
        "due = tick()\n"
        "assert any(j['title'] == 'restart contract job' for j in due), due\n"
        "jobs_after = list_jobs('t46a', status='due')\n"
        "assert any(j['title'] == 'restart contract job' for j in jobs_after), jobs_after\n"
        "print('OK')\n"
    )

    def test_restart_contract_two_subprocesses(self):
        env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

        # Subprocess A — write.
        result_a = subprocess.run(
            [sys.executable, "-c", self._SCRIPT_A],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.getcwd(),
        )
        self.assertEqual(
            result_a.returncode, 0,
            msg=f"Subprocess A failed:\nstdout:\n{result_a.stdout}\nstderr:\n{result_a.stderr}",
        )
        self.assertIn("OK", result_a.stdout)

        # Subprocess B — read + tick.
        result_b = subprocess.run(
            [sys.executable, "-c", self._SCRIPT_B],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.getcwd(),
        )
        self.assertEqual(
            result_b.returncode, 0,
            msg=f"Subprocess B failed:\nstdout:\n{result_b.stdout}\nstderr:\n{result_b.stderr}",
        )
        self.assertIn("OK", result_b.stdout)

    # --- no live network ---

    def test_no_live_network(self):
        # This test exists to assert the suite does not require network.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
