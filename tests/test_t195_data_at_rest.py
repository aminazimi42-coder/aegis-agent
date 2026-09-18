"""Tests for T195 — optional SQLite encryption at rest, default off."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest import TestCase


class DataAtRestTests(TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._old_data_dir = os.environ.get("AEGIS_DATA_DIR")
        self._old_encrypt = os.environ.get("AEGIS_DATA_ENCRYPT")
        self._old_pass = os.environ.get("AEGIS_DATA_PASSPHRASE")
        os.environ["AEGIS_DATA_DIR"] = str(self._tmp)
        os.environ.pop("AEGIS_DATA_ENCRYPT", None)
        os.environ.pop("AEGIS_DATA_PASSPHRASE", None)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)
        for key in ("AEGIS_DATA_DIR", "AEGIS_DATA_ENCRYPT", "AEGIS_DATA_PASSPHRASE"):
            if self._old_data_dir is not None and key == "AEGIS_DATA_DIR":
                os.environ[key] = self._old_data_dir
            else:
                os.environ.pop(key, None)

    # ------------------------------------------------------------------ #
    # test_default_encrypt_off_opens_plaintext
    # ------------------------------------------------------------------ #
    def test_default_encrypt_off_opens_plaintext(self) -> None:
        """When AEGIS_DATA_ENCRYPT is unset, the path stays plaintext."""
        from core import data_at_rest as dar

        os.environ.pop("AEGIS_DATA_ENCRYPT", None)
        db = dar._db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"plaintext-sqlite-content")
        assert not dar.encrypt_enabled()
        # read_encrypted_db_bytes returns plaintext contents directly
        assert dar.read_encrypted_db_bytes() == b"plaintext-sqlite-content"
        # No encrypted blob is created
        assert not dar._enc_path().exists()

    # ------------------------------------------------------------------ #
    # test_encrypt_on_without_passphrase_typed_fail
    # ------------------------------------------------------------------ #
    def test_encrypt_on_without_passphrase_typed_fail(self) -> None:
        """AEGIS_DATA_ENCRYPT=1 without a passphrase raises a typed error."""
        from core import data_at_rest as dar

        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ.pop("AEGIS_DATA_PASSPHRASE", None)
        with self.assertRaises(dar.DataAtRestError):
            dar._require_passphrase()
        with self.assertRaises(dar.DataAtRestError):
            dar.read_encrypted_db_bytes()

    # ------------------------------------------------------------------ #
    # test_encrypt_roundtrip_with_passphrase
    # ------------------------------------------------------------------ #
    def test_encrypt_roundtrip_with_passphrase(self) -> None:
        """Encrypt then decrypt roundtrips the SQLite bytes."""
        from core import data_at_rest as dar

        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ["AEGIS_DATA_PASSPHRASE"] = "secret-passphrase-42"

        payload = b"-- sqlite db bytes --"
        dar.write_encrypted_db_bytes(payload)
        assert dar.read_encrypted_db_bytes() == payload
        # The encrypted blob is on disk and is not the raw plaintext.
        blob = dar._enc_path().read_bytes()
        assert blob != payload
        assert dar._enc_path().exists()

    # ------------------------------------------------------------------ #
    # test_wrong_passphrase_typed_fail
    # ------------------------------------------------------------------ #
    def test_wrong_passphrase_typed_fail(self) -> None:
        """A wrong passphrase raises a typed DataAtRestError."""
        from core import data_at_rest as dar

        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ["AEGIS_DATA_PASSPHRASE"] = "correct-password"
        dar.write_encrypted_db_bytes(b"some-data")

        os.environ["AEGIS_DATA_PASSPHRASE"] = "wrong-password"
        with self.assertRaises(dar.DataAtRestError):
            dar.read_encrypted_db_bytes()

    # ------------------------------------------------------------------ #
    # test_plaintext_migrates_only_when_encrypt_on
    # ------------------------------------------------------------------ #
    def test_plaintext_migrates_only_when_encrypt_on(self) -> None:
        """A plaintext SQLite file migrates to encrypted when ENCRYPT=1."""
        from core.data_at_rest import ensure_encrypted

        # Start plaintext.
        db = Path(os.environ["AEGIS_DATA_DIR"]) / "aegis.sqlite"
        db.write_bytes(b"plain-sqlite")
        assert db.exists()

        # Turn on encryption.
        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ["AEGIS_DATA_PASSPHRASE"] = "migrate-pass"

        enc_path = ensure_encrypted()
        assert enc_path.suffix == ".enc"
        assert enc_path.exists()

        # The original plaintext is deleted; a .bak is kept.
        assert not db.exists()
        bak = Path(os.environ["AEGIS_DATA_DIR"]) / "aegis.sqlite.bak"
        assert bak.exists()
        assert bak.read_bytes() == b"plain-sqlite"

        # Encrypted blob is not the raw plaintext.
        assert enc_path.read_bytes() != b"plain-sqlite"

    # ------------------------------------------------------------------
    # test_passphrase_not_written_to_repo_or_receipt_fixture
    # ------------------------------------------------------------------
    def test_passphrase_not_written_to_repo_or_receipt_fixture(self) -> None:
        """The passphrase is never written to disk by the at-rest module."""
        from core import data_at_rest as dar

        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ["AEGIS_DATA_PASSPHRASE"] = "never-on-disk-123"
        dar.write_encrypted_db_bytes(b"payload")

        # Scan every file under the data dir for the passphrase string.
        for p in Path(os.environ["AEGIS_DATA_DIR"]).rglob("*"):
            if p.is_file():
                assert b"never-on-disk-123" not in p.read_bytes(), (
                    f"passphrase found in {p}"
                )

    # ------------------------------------------------------------------
    # test_encrypted_blob_stays_inside_data_dir
    # ------------------------------------------------------------------
    def test_encrypted_blob_stays_inside_data_dir(self) -> None:
        """The encrypted blob is written inside AEGIS_DATA_DIR only."""
        from core import data_at_rest as dar

        os.environ["AEGIS_DATA_ENCRYPT"] = "1"
        os.environ["AEGIS_DATA_PASSPHRASE"] = "cage-pass-1"
        dar.write_encrypted_db_bytes(b"inside-data")

        enc = dar._enc_path()
        assert enc.exists()
        root = Path(os.environ["AEGIS_DATA_DIR"]).resolve()
        assert enc.resolve().is_relative_to(root)

    # ------------------------------------------------------------------
    # test_readme_author_untouched
    # ------------------------------------------------------------------
    def test_readme_author_untouched(self) -> None:
        """README.md still contains the Author paragraph."""
        readme = Path("README.md").read_text()
        assert "Author" in readme
        assert "Amin Azimi" in readme

    # ------------------------------------------------------------------
    # test_readme_does_not_contain_notarized
    # ------------------------------------------------------------------
    def test_readme_does_not_contain_notarized(self) -> None:
        """README.md does not contain the word 'notarized'."""
        readme = Path("README.md").read_text().lower()
        assert "notarized" not in readme
