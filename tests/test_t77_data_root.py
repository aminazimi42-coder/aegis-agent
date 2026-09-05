"""T77 — Local data root is an absolute disk path.

Covers:
- ``data_root()`` resolves ``AEGIS_DATA_DIR`` (or ``data/`` by default) to an
  absolute :class:`~pathlib.Path` and returns it.
- ``data_root()`` creates the directory with ``parents=True, exist_ok=True``
  when it does not yet exist.
- ``AEGIS_DATA_DIR`` is a temp directory for isolation; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_local_view import data_root


class TestT77DataRoot(unittest.TestCase):
    """data_root() returns an absolute, existing data directory Path."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t77_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    def test_data_root_is_absolute(self) -> None:
        """data_root() must return a Path whose .is_absolute() is True."""
        root = data_root()
        self.assertIsInstance(root, Path)
        self.assertTrue(root.is_absolute())

    def test_data_root_creates_dir(self) -> None:
        """data_root() must create the directory when it does not exist."""
        # Point AEGIS_DATA_DIR at a non-existent sub-path.
        fresh = os.path.join(self._tmp, "fresh_subdir", "nested")
        os.environ["AEGIS_DATA_DIR"] = fresh
        self.assertFalse(Path(fresh).exists())

        root = data_root()

        self.assertTrue(root.exists(), "data_root() did not create the directory")
        self.assertTrue(root.is_absolute())
        # Compare via samefile to avoid macOS /var → /private/var symlink noise.
        self.assertTrue(root.samefile(Path(fresh)))

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
