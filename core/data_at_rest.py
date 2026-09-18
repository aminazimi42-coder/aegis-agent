"""Optional encryption at rest for the tenant SQLite file (T195).

When ``AEGIS_DATA_ENCRYPT=1`` and ``AEGIS_DATA_PASSPHRASE`` is set in
the process environment, the SQLite database file under
``AEGIS_DATA_DIR`` is stored as an encrypted blob.  Default (unset or
``0``) keeps the database plaintext so existing stores keep opening.

No passphrase is ever written to README, STATUS, receipts, audit
JSONL, operator HTML, session receipts, or fixtures.

The encrypted blob stays inside ``AEGIS_DATA_DIR``.  Paths outside the
data dir are rejected through the T190 ``cage_path`` helper.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT_LEN = 16
_KDF_ITERATIONS = 480_000


class DataAtRestError(ValueError):
    """Typed rejection from the data-at-rest module."""


def _data_root() -> Path:
    """Return the resolved data root from ``AEGIS_DATA_DIR``."""

    raw = os.getenv("AEGIS_DATA_DIR", "data")
    root = Path(raw)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _db_path() -> Path:
    """Return the plaintext SQLite path (same as T194 ``aegis.sqlite``)."""
    return _data_root() / "aegis.sqlite"


def _enc_path() -> Path:
    """Return the encrypted-blob path inside the data dir."""
    return _data_root() / "aegis.sqlite.enc"


def _bak_path() -> Path:
    """Return the migration backup path inside the data dir."""
    return _data_root() / "aegis.sqlite.bak"


def encrypt_enabled() -> bool:
    """Return True when ``AEGIS_DATA_ENCRYPT=1`` in the environment."""
    return os.getenv("AEGIS_DATA_ENCRYPT", "").strip() in {"1", "true", "yes"}


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a Fernet key from *passphrase* and *salt* via PBKDF2-HMAC-SHA256."""
    import base64

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    raw = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _encrypt_bytes(passphrase: str, plaintext: bytes) -> bytes:
    """Encrypt *plaintext* with a fresh random salt; prepend salt to the blob."""
    salt = os.urandom(_SALT_LEN)
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    return salt + f.encrypt(plaintext)


def _decrypt_bytes(passphrase: str, blob: bytes) -> bytes:
    """Decrypt *blob* (salt-prefixed); raise ``DataAtRestError`` on failure."""
    if len(blob) < _SALT_LEN:
        raise DataAtRestError("encrypted blob too short")
    salt = blob[:_SALT_LEN]
    ciphertext = blob[_SALT_LEN:]
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    try:
        return f.decrypt(ciphertext)
    except Exception as exc:
        raise DataAtRestError("wrong passphrase or corrupted blob") from exc


def encrypt_file(path: Path, passphrase: str) -> bytes:
    """Encrypt the file at *path* and return the ciphertext bytes.

    The original file is left in place; the caller decides whether to
    move or delete it.
    """
    plaintext = Path(path).read_bytes()
    return _encrypt_bytes(passphrase, plaintext)


def decrypt_file_blob(passphrase: str, blob: bytes) -> bytes:
    """Decrypt an encrypted blob (in memory) and return the plaintext bytes."""
    return _decrypt_bytes(passphrase, blob)


def _require_passphrase() -> str:
    """Return the passphrase from the environment or raise a typed error."""
    pw = os.getenv("AEGIS_DATA_PASSPHRASE", "")
    if not pw or not pw.strip():
        raise DataAtRestError(
            "AEGIS_DATA_ENCRYPT=1 but AEGIS_DATA_PASSPHRASE is missing or empty"
        )
    return pw


def _cage(path: Path) -> Path:
    """Resolve *path* through the T190 ``cage_path`` helper."""
    from core.twin_local_view import cage_path

    return cage_path(path)


def ensure_encrypted() -> Path:
    """Ensure the SQLite file is in encrypted form when ENCRYPT=1.

    Returns the path to the encrypted blob (or the plaintext file when
    encryption is off).  When a plaintext SQLite file already exists and
    encryption is on, a one-time local migration runs:

    1. Write the encrypted blob to ``aegis.sqlite.enc``.
    2. Copy the original plaintext to ``aegis.sqlite.bak``.
    3. Verify the encrypted file decrypts before deleting the original.
    """
    from core.twin_local_view import cage_path

    if not encrypt_enabled():
        return _db_path()

    passphrase = _require_passphrase()
    db = _db_path()
    enc = _enc_path()

    # If an encrypted blob already exists, just return it.
    if enc.exists():
        cage_path(enc)
        return enc

    # No plaintext file — nothing to migrate; create an empty encrypted
    # blob so subsequent reads/writes stay consistent.
    if not db.exists():
        empty_enc = _encrypt_bytes(passphrase, b"")
        enc.write_bytes(empty_enc)
        return enc

    # Migration: encrypt the existing plaintext file.
    plaintext_bytes = db.read_bytes()
    blob = _encrypt_bytes(passphrase, plaintext_bytes)

    # Write the encrypted blob.
    enc.write_bytes(blob)

    # Verify the encrypted file decrypts before deleting the original.
    roundtrip = _decrypt_bytes(passphrase, enc.read_bytes())
    if roundtrip != plaintext_bytes:
        # Verification failed — do not delete the original.
        enc.unlink(missing_ok=True)
        raise DataAtRestError("encryption verification failed; original kept")

    # Keep a .bak copy of the plaintext inside the data dir.
    _bak_path().write_bytes(plaintext_bytes)

    # Delete the original plaintext only after the encrypted file verifies.
    db.unlink()

    return enc


def read_encrypted_db_bytes() -> bytes:
    """Return the decrypted SQLite bytes for the current configuration.

    When encryption is off, reads the plaintext file directly.  When on,
    decrypts the ``aegis.sqlite.enc`` blob using the process passphrase.
    """
    if not encrypt_enabled():
        return _db_path().read_bytes()

    passphrase = _require_passphrase()
    enc = _enc_path()
    if not enc.exists():
        # Fall back to plaintext if a plaintext file exists but no
        # encrypted blob does (e.g. migration not yet run).
        if _db_path().exists():
            return _db_path().read_bytes()
        raise DataAtRestError("encrypted database file not found")
    return _decrypt_bytes(passphrase, enc.read_bytes())


def write_encrypted_db_bytes(data: bytes) -> None:
    """Write *data* as the SQLite file content for the current configuration.

    When encryption is off, writes plaintext.  When on, writes the
    encrypted blob.  The blob always stays inside ``AEGIS_DATA_DIR``.
    """
    from core.twin_local_view import cage_path

    if not encrypt_enabled():
        p = _db_path()
        cage_path(p)
        p.write_bytes(data)
        return

    passphrase = _require_passphrase()
    enc = _enc_path()
    cage_path(enc)
    blob = _encrypt_bytes(passphrase, data)
    enc.write_bytes(blob)


def get_passphrase() -> Optional[str]:
    """Return the passphrase or ``None`` when unset (test helper)."""
    pw = os.getenv("AEGIS_DATA_PASSPHRASE", "")
    return pw if pw.strip() else None
