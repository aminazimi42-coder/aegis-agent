"""Local fourteen-day eval pack — marker, manifest, and Echo-limited expiry (T231).

A local eval pack can be marked as a fourteen-day trial.  The pack contains the
operator app files only — it must **not** contain ``.git``, the owner ``.aegis``
data directory, or a Hermes directive (``_directive.txt``).

Eval marker
-----------
:func:`create_eval_marker` writes a JSON marker under
``AEGIS_DATA_DIR/eval_markers/{tenant_id}.json`` with fields:

* ``tenant_id``   — the tenant this marker is bound to
* ``started_at``  — ISO-8601 UTC timestamp
* ``ends_at``     — ``started_at`` plus 14 days
* ``status``      — ``"active"`` or ``"expired"``

No network call is made.

Expiry
------
:func:`eval_entitlement` checks the marker for *tenant_id*.  When ``now`` is
after ``ends_at`` the tier returns **Echo-limited** with reason
``eval_expired``.  The marker file **stays** on disk — it is never deleted.
Profile, receipts, and export stay.  A **missing** marker stays the existing
``missing_file`` Echo-limited path (it does **not** crash).

Cross-tenant
-------------
The marker path is keyed by ``tenant_id``; a neighbour tenant cannot read
another tenant's marker.

Pack manifest
-------------
:func:`pack_manifest` returns the list of operator file paths from a source
directory, excluding ``.git``, ``_directive.txt``, and any path under the
owner ``.aegis`` data dir.

Locks
-----
* Six specialists only — no seventh agent.
* Echo default; missing / expired / cancelled entitlement stays Echo-limited.
* Card network and checkout stay outside execute; ``core/`` has no card token.
* No network call.
* ``start_operator.sh`` remains the only operator start path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root

# Fourteen-day eval window.
EVAL_DAYS: int = 14

# Directories excluded from the pack manifest.
_PACK_EXCLUDE_TOP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        ".cache",
        ".ruff_cache",
        ".pytest_cache",
        ".kms",
        ".market",
        ".agents.db",
        "dist",
        "node_modules",
    }
)

# Files excluded from the pack manifest (by basename).
_PACK_EXCLUDE_FILES: frozenset[str] = frozenset(
    {
        "_directive.txt",
        ".DS_Store",
    }
)


class EvalPackError(RuntimeError):
    """Typed failure for the eval-pack path."""


def _markers_dir() -> Path:
    """Return the directory holding eval markers under ``AEGIS_DATA_DIR``."""
    return data_root() / "eval_markers"


def _marker_path(tenant_id: str) -> Path:
    """Return the path to the eval marker for *tenant_id*."""
    if not tenant_id:
        raise EvalPackError("tenant_id is required")
    # Sanitize — only alnum, dash, underscore in the filename.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
    return _markers_dir() / f"{safe}.json"


def create_eval_marker(
    tenant_id: str,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a fourteen-day eval marker under ``AEGIS_DATA_DIR``.

    *started_at* defaults to ``datetime.now(timezone.utc)``.  ``ends_at`` is
    *started_at* plus :data:`EVAL_DAYS` (14 days).  The marker is written as
    JSON under ``eval_markers/{tenant_id}.json`` and returned as a dict.

    No network call is made.
    """
    if not tenant_id:
        raise EvalPackError("tenant_id is required")
    now = started_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ends_at = now + timedelta(days=EVAL_DAYS)
    marker: dict[str, Any] = {
        "tenant_id": tenant_id,
        "started_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
        "status": "active",
    }
    d = _markers_dir()
    d.mkdir(parents=True, exist_ok=True)
    _marker_path(tenant_id).write_text(
        json.dumps(marker, indent=2), encoding="utf-8"
    )
    return marker


def read_eval_marker(tenant_id: str) -> dict[str, Any] | None:
    """Read the eval marker for *tenant_id*.

    Returns ``None`` when the marker is missing, unreadable, or malformed.
    A marker whose ``tenant_id`` field does not match *tenant_id* returns
    ``None`` — a neighbour tenant cannot read another tenant's marker.
    """
    path = _marker_path(tenant_id)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    file_tenant = data.get("tenant_id")
    if not isinstance(file_tenant, str) or file_tenant != tenant_id:
        return None
    return data


def _is_past(ends_at: Any) -> bool:
    """Return True when *ends_at* is a past ISO-UTC string."""
    if not isinstance(ends_at, str) or not ends_at:
        return True
    try:
        dt = datetime.fromisoformat(ends_at)
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > dt


def eval_entitlement(tenant_id: str) -> dict[str, Any]:
    """Return the eval-influenced entitlement for *tenant_id*.

    * **Missing marker** — stays the existing ``missing_file`` Echo-limited
      path (falls through to :func:`core.entitlement.load`).  Does not crash.
    * **Active marker** (``now <= ends_at``) — returns
      ``{"tier": "echo", "reason": "eval_active", ...}``.
    * **Expired marker** (``now > ends_at``) — returns Echo-limited with
      ``reason="eval_expired"``.  The marker file **stays** on disk; its
      ``status`` is updated to ``"expired"``.  Profile, receipts, and export
      are not deleted.

    No network call is made.
    """
    marker = read_eval_marker(tenant_id)
    if marker is None:
        # Missing marker — stay the existing missing-file Echo-limited path.
        from core.entitlement import load

        return load(tenant_id)
    ends_at = marker.get("ends_at")
    if _is_past(ends_at):
        # Expired — update status in-place but do NOT delete the file.
        marker["status"] = "expired"
        try:
            _marker_path(tenant_id).write_text(
                json.dumps(marker, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # marker file stays even if we can't update it
        return {"tier": "echo", "reason": "eval_expired", "eval": marker}
    return {"tier": "echo", "reason": "eval_active", "eval": marker}


def pack_manifest(source_dir: str | Path) -> list[str]:
    """Return the list of operator file paths from *source_dir*.

    The manifest lists **operator files only** — it excludes:

    * ``.git`` (and any path inside a ``.git`` directory)
    * ``_directive.txt``
    * any path that resolves inside the owner ``.aegis`` data dir
      (``AEGIS_DATA_DIR``)
    * build/cache artefacts (``__pycache__``, ``.venv``, ``.cache``,
      ``.ruff_cache``, ``.pytest_cache``, ``dist``)

    No network call is made.
    """
    src = Path(source_dir).resolve()
    root = data_root().resolve()
    files: list[str] = []
    for entry in sorted(src.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(src)
        parts = rel.parts
        # Exclude .git (any depth).
        if ".git" in parts:
            continue
        # Exclude _directive.txt (any depth).
        if rel.name == "_directive.txt":
            continue
        # Exclude any path that resolves inside the owner .aegis data dir.
        try:
            entry.resolve().relative_to(root)
            continue  # inside data dir — excluded
        except ValueError:
            pass
        # Exclude build/cache top-level dirs.
        if parts and parts[0] in _PACK_EXCLUDE_TOP_DIRS:
            continue
        # Exclude excluded basenames.
        if rel.name in _PACK_EXCLUDE_FILES:
            continue
        files.append(str(rel))
    return files
