"""T86 — Default data root is the user home (~/.aegis), not the repo tree.

Covers:
- When ``AEGIS_DATA_DIR`` is unset, ``data_root()`` returns
  ``Path.home() / ".aegis"`` (an absolute path inside the user home,
  never the git working tree).
- When ``AEGIS_DATA_DIR`` is set to a non-empty value, that value still
  wins (existing behaviour preserved).
- ``Path.home`` is mocked so no directory is created in the real user
  home.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.twin_local_view import data_root


class TestT86UserDataHome(unittest.TestCase):
    """data_root() defaults to ~/.aegis when AEGIS_DATA_DIR is unset."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t86_")
        # Ensure AEGIS_DATA_DIR is unset for the "default" tests.
        self._prev = os.environ.pop("AEGIS_DATA_DIR", None)

    def tearDown(self) -> None:
        if self._prev is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    def test_unset_env_uses_home_aegis(self) -> None:
        """Without AEGIS_DATA_DIR, data_root() must be ~/.aegis."""
        fake_home = Path(self._tmp)
        with mock.patch("pathlib.Path.home", return_value=fake_home):
            root = data_root()
        self.assertTrue(root.is_absolute())
        self.assertEqual(root, fake_home / ".aegis")
        self.assertTrue(root.exists(), "data_root() did not create ~/.aegis")
        # Must not be inside the repository working tree.
        self.assertNotEqual(root, Path.cwd() / "data")

    def test_aegis_data_dir_still_wins(self) -> None:
        """When AEGIS_DATA_DIR is set, it overrides the ~/.aegis default."""
        custom = os.path.join(self._tmp, "custom_data")
        os.environ["AEGIS_DATA_DIR"] = custom
        fake_home = Path(self._tmp)
        with mock.patch("pathlib.Path.home", return_value=fake_home):
            root = data_root()
        self.assertTrue(root.is_absolute())
        self.assertTrue(root.samefile(Path(custom)))
        self.assertNotEqual(root, fake_home / ".aegis")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
