"""Local pack update — copy/replace operator pack files without touching the data dir.

T230 — an operator-pack update can replace the local app files (app code, start
script, version marker) and **must not** delete, move, or rewrite the operator
data directory under ``AEGIS_DATA_DIR``.  Profile, actions, receipts, and export
files stay byte-stable across the update.

Locks:
* ``apply_pack_update`` **refuses** to run when the target path is inside
  ``AEGIS_DATA_DIR`` — the update code never writes into the data dir.
* Before replace, a fingerprint of the data dir is recorded.  After replace,
  the same fingerprint is checked and a mismatch is a typed fail that aborts.
* The update does **not** delete ``export/``, ``receipts/``, or
  ``purchase_receipts/``.  It does **not** clear ``entitlement.json``.
* No network call is made.
* The update does **not** set ``AEGIS_DATA_DIR`` to the pack folder.
* ``core/`` has no card-network token.

The data fingerprint is the tuple ``(profile file size + sha256, receipt count,
entitlement.json present, export file count)`` — stable across a code-only update.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root


class PackUpdateError(RuntimeError):
    """Typed failure for the pack-update path."""


class PathInsideDataDirError(PackUpdateError):
    """Typed deny when the target path resolves inside ``AEGIS_DATA_DIR``."""

    code: str = "path_inside_data_dir"


class FingerprintMismatchError(PackUpdateError):
    """Typed fail when the data-dir fingerprint changes across the update."""

    code: str = "data_fingerprint_mismatch"


def data_fingerprint() -> dict[str, Any]:
    """Return a stable fingerprint of the data dir.

    The fingerprint is a dict with:
        profile_size      — int, byte size of profile.json (0 when missing)
        profile_sha256    — hex digest of profile.json ("" when missing)
        receipt_count     — int, number of files in receipts/
        purchase_count    — int, number of files in purchase_receipts/
        entitlement_present — bool, entitlement.json exists
        export_count      — int, number of files in export/
    """
    root = data_root()
    profile = root / "profile.json"
    if profile.is_file():
        raw = profile.read_bytes()
        profile_size = len(raw)
        profile_sha = hashlib.sha256(raw).hexdigest()
    else:
        profile_size = 0
        profile_sha = ""
    receipts = root / "receipts"
    receipt_count = len(list(receipts.iterdir())) if receipts.is_dir() else 0
    purchase_receipts = root / "purchase_receipts"
    purchase_count = (
        len(list(purchase_receipts.iterdir())) if purchase_receipts.is_dir() else 0
    )
    entitlement_present = (root / "entitlement.json").is_file()
    export_dir = root / "export"
    export_count = len(list(export_dir.iterdir())) if export_dir.is_dir() else 0
    return {
        "profile_size": profile_size,
        "profile_sha256": profile_sha,
        "receipt_count": receipt_count,
        "purchase_count": purchase_count,
        "entitlement_present": entitlement_present,
        "export_count": export_count,
    }


def _resolve_target(target: str | Path) -> Path:
    """Resolve *target* and deny when it is inside ``AEGIS_DATA_DIR``."""
    root = data_root()
    dest = Path(target).resolve()
    try:
        dest.relative_to(root.resolve())
    except ValueError:
        pass  # outside data dir — allowed
    else:
        raise PathInsideDataDirError(
            f"target {dest} is inside AEGIS_DATA_DIR {root}"
        ) from None
    return dest


def apply_pack_update(
    pack_dir: str | Path,
    target: str | Path,
    version_marker: str = "",
) -> dict[str, Any]:
    """Copy or replace operator pack files from *pack_dir* into *target*.

    *pack_dir* is the source pack folder (app code, start script, version
    marker).  *target* is the destination — the local operator install path.

    The function **refuses** to run when *target* is inside ``AEGIS_DATA_DIR``.
    Before the replace, a fingerprint of the data dir is recorded.  After the
    replace, the same fingerprint is checked — a mismatch is a typed fail that
    aborts the update.

    No network call is made.  No file under ``AEGIS_DATA_DIR`` is deleted,
    moved, or rewritten.  ``AEGIS_DATA_DIR`` is not set to the pack folder.

    Returns a dict with:
        ok            — True when the update applied cleanly
        before        — data fingerprint before replace
        after         — data fingerprint after replace
        fingerprint_match — True when before == after
        target        — resolved target path
        version_marker  — the version marker written
    """
    pack = Path(pack_dir)
    if not pack.is_dir():
        raise PackUpdateError(f"pack dir {pack} does not exist")
    # Resolve and cage the target — refuse inside data dir.
    dest = _resolve_target(target)
    # Record the data-dir fingerprint BEFORE replace.
    before = data_fingerprint()
    # Copy/replace only the operator pack files (app code, start script,
    # version marker).  We copy the pack contents into the target — we do
    # not touch AEGIS_DATA_DIR.
    dest.mkdir(parents=True, exist_ok=True)
    for entry in pack.iterdir():
        dst = dest / entry.name
        if entry.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(entry, dst)
        else:
            shutil.copy2(entry, dst)
    # Write the version marker.
    marker = version_marker or datetime.now(timezone.utc).isoformat()
    (dest / "VERSION").write_text(marker + "\n", encoding="utf-8")
    # Record the data-dir fingerprint AFTER replace.
    after = data_fingerprint()
    match = before == after
    if not match:
        raise FingerprintMismatchError(
            f"data fingerprint changed: before={before} after={after}"
        )
    return {
        "ok": True,
        "before": before,
        "after": after,
        "fingerprint_match": match,
        "target": str(dest),
        "version_marker": marker,
    }
