"""T34 — Audio sidecar to a proposed twin task.

Covers:
- from_audio without a consented profile raises ValueError.
- from_audio with a missing audio file raises ValueError.
- from_audio with a missing .txt sidecar raises ValueError.
- After a T03 commit, sidecar transcript "Call the Berlin hotel tonight":
  result title or markdown contains "Berlin hotel".
- FastAPI 200 on POST /api/v1/twin/audio/task.
- No live network / no paid LLM / no audio decode.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_audio_task import from_audio
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT34TwinAudioTask(unittest.TestCase):
    """Audio sidecar → proposed task invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_from_audio_without_profile_raises_value_error(self) -> None:
        wav = Path(self._tmp) / "note.wav"
        wav.write_bytes(b"dummy audio bytes")
        txt = Path(self._tmp) / "note.txt"
        txt.write_text("Call the Berlin hotel tonight", encoding="utf-8")
        with self.assertRaises(ValueError):
            from_audio("no_profile_t34", str(wav))

    def test_from_audio_missing_audio_raises_value_error(self) -> None:
        self._full_interview("t34_missing_audio")
        with self.assertRaises(ValueError):
            from_audio(
                "t34_missing_audio",
                str(Path(self._tmp) / "nonexistent.wav"),
            )

    def test_from_audio_missing_sidecar_raises_value_error(self) -> None:
        self._full_interview("t34_missing_sidecar")
        wav = Path(self._tmp) / "note.wav"
        wav.write_bytes(b"dummy audio bytes")
        # No .txt sidecar next to it.
        with self.assertRaises(ValueError):
            from_audio("t34_missing_sidecar", str(wav))

    def test_from_audio_writes_berlin_hotel(self) -> None:
        self._full_interview("t34a")
        wav = Path(self._tmp) / "dummy.wav"
        wav.write_bytes(b"dummy audio bytes")
        txt = Path(self._tmp) / "dummy.txt"
        txt.write_text("Call the Berlin hotel tonight", encoding="utf-8")

        result = from_audio("t34a", str(wav))

        self.assertEqual(result["tenant_id"], "t34a")
        self.assertTrue(result["action_id"])
        self.assertEqual(result["title"], "Call the Berlin hotel tonight")
        self.assertEqual(result["sidecar"], "dummy.txt")

        md_path = Path(result["path"])
        self.assertTrue(md_path.exists())
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("Berlin hotel", text)
        self.assertIn("dummy.txt", text)
        self.assertIn(result["action_id"], text)

    def test_fastapi_audio_task_200(self) -> None:
        self._full_interview("t34f")
        wav = Path(self._tmp) / "dummy.wav"
        wav.write_bytes(b"dummy audio bytes")
        txt = Path(self._tmp) / "dummy.txt"
        txt.write_text("Call the Berlin hotel tonight", encoding="utf-8")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/audio/task",
            json={
                "tenant_id": "t34f",
                "audio_path": str(wav),
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t34f")
        self.assertTrue(body["action_id"])
        self.assertIn("Berlin hotel", body["title"])
        self.assertEqual(body["sidecar"], "dummy.txt")

    def test_fastapi_audio_task_400_without_profile(self) -> None:
        wav = Path(self._tmp) / "note.wav"
        wav.write_bytes(b"dummy audio bytes")
        txt = Path(self._tmp) / "note.txt"
        txt.write_text("hello", encoding="utf-8")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/audio/task",
            json={
                "tenant_id": "no_profile_t34_api",
                "audio_path": str(wav),
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
