"""Encrypted inter-Mac portable bundle (T197).

``write_portable_bundle(tenant_id)`` creates a single encrypted
``portable_YYYYMMDDThhmmssZ.aegis`` archive under
``AEGIS_DATA_DIR/export/`` containing that tenant's profile, actions,
jobs, and receipts (same T69 snapshot).  The archive is encrypted with
the T195 Fernet construction when ``AEGIS_DATA_PASSPHRASE`` is set.
A missing passphrase is a typed fail — no file is written.

``import_portable_bundle(tenant_id, src)`` decrypts and restores the
bundle into ``AEGIS_DATA_DIR``.  A wrong passphrase, truncated file,
empty file, or missing auth tag is a typed fail; the destination
tenant is left unchanged on failure.  Imported actions stay
proposed/approved as stored — the human still Approves before execute.

The write uses a sibling temp name, fsync, then atomic rename.  If the
process is killed before rename, the final ``portable_*.aegis`` name
does not exist.  A disk-full (ENOSPC) during write is a typed fail and
leaves no valid ``portable_*.aegis`` behind.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.data_at_rest import DataAtRestError, decrypt_file_blob, encrypt_file, get_passphrase
from core.twin_backup import backup_tenant, restore_tenant
from core.twin_local_view import cage_path, data_root


class PortableBundleError(ValueError):
    """Typed rejection from the portable-bundle module."""

    code: str = "portable_bundle_error"


def _export_dir() -> Path:
    """Return the export directory under the data root."""
    d = data_root() / "export"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_portable_bundle(tenant_id: str) -> Path:
    """Write one encrypted portable bundle under ``AEGIS_DATA_DIR/export/``.

    The bundle is named ``portable_YYYYMMDDThhmmssZ.aegis`` and contains
    the T69 tenant snapshot (profile, actions, jobs, receipts) encrypted
    with the T195 Fernet construction.

    Requires ``AEGIS_DATA_PASSPHRASE`` — a missing passphrase is a
    typed :class:`PortableBundleError` with no file written.

    The write goes to a sibling temp name first, then fsync, then atomic
    rename.  If the process is killed before rename, the final
    ``portable_*.aegis`` name does not exist.  A disk-full (ENOSPC)
    during write is a typed fail and leaves no valid bundle behind.
    """
    passphrase = get_passphrase()
    if not passphrase:
        raise PortableBundleError("missing passphrase; set AEGIS_DATA_PASSPHRASE")

    export_dir = _export_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_name = f"portable_{stamp}.aegis"
    final_path = cage_path(export_dir / final_name)

    # Build the plaintext zip using T69 backup_tenant.
    zip_tmp = export_dir / f"_portable_{stamp}_{uuid.uuid4().hex[:8]}.zip"
    tmp_path = final_path.parent / (final_path.name + ".tmp")
    try:
        backup_tenant(tenant_id, zip_tmp)
        blob = encrypt_file(zip_tmp, passphrase)

        with open(tmp_path, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())  # may raise OSError(ENOSPC)
        os.replace(tmp_path, final_path)
    except OSError as exc:
        # Disk-full or other OS error: clean up temp, no valid .aegis.
        tmp_path.unlink(missing_ok=True)
        raise PortableBundleError(f"write failed: {exc}") from exc
    finally:
        zip_tmp.unlink(missing_ok=True)

    return final_path


def import_portable_bundle(tenant_id: str, src: str | Path) -> dict[str, Any]:
    """Decrypt and restore a portable bundle into ``AEGIS_DATA_DIR``.

    A wrong passphrase, truncated file, empty file, or missing auth tag
    is a typed :class:`PortableBundleError`; the destination tenant is
    left unchanged on failure.  Imported actions stay proposed/approved
    as stored — no auto-execute.
    """
    passphrase = get_passphrase()
    if not passphrase:
        raise PortableBundleError("missing passphrase; set AEGIS_DATA_PASSPHRASE")

    src_path = Path(src)
    if not src_path.is_file():
        raise PortableBundleError("bundle file not found")

    blob = src_path.read_bytes()
    if not blob:
        raise PortableBundleError("empty bundle")

    try:
        plaintext = decrypt_file_blob(passphrase, blob)
    except DataAtRestError as exc:
        raise PortableBundleError(
            f"wrong passphrase or corrupted bundle: {exc}"
        ) from exc

    # Write decrypted zip to a temp file under the data dir, then restore.
    root = data_root()
    fd, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=str(root))
    os.close(fd)
    zip_path = Path(tmp_zip)
    try:
        zip_path.write_bytes(plaintext)
        result = restore_tenant(tenant_id, zip_path)
    finally:
        zip_path.unlink(missing_ok=True)

    return result
