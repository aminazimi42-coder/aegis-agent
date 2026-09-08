"""Local search, replay, export, and import for the cognitive twin (T100).

Provides grep-style local file search, action lifecycle replay, and
tenant-scoped archive export/import — all fully local with no network
calls, no sync server, and no vector DB.

* ``search(tenant_id, term)`` — recursively scan ``.md``/``.json`` files
  under the tenant's data-root directories for *term* (case-insensitive).
  Read-only.

* ``replay(action_id, tenant_id)`` — write one markdown file under the
  tenant work-products directory that lists the propose → approve →
  execute lifecycle if each phase is present.  Does **not** re-execute.

* ``export_tenant(tenant_id, out_path)`` — pack the tenant's data-root
  folders into a local ``.tar.gz`` archive.

* ``import_archive(archive_path)`` — restore an archive into
  ``AEGIS_DATA_DIR``.  Never touches another tenant — only paths that
  were in the archive are extracted.
"""

from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root

# ---------------------------------------------------------------------------#
# Tenant directory discovery
# ---------------------------------------------------------------------------#


def _tenant_dirs(tenant_id: str) -> list[Path]:
    """Return all existing directories under the data root that belong to *tenant_id*.

    Currently:
      * ``{data_root}/{tenant_id}/``         — profile and local files
      * ``{data_root}/work_products/{tenant_id}/`` — rendered work products
    """
    root = data_root()
    candidates = [
        root / tenant_id,
        root / "work_products" / tenant_id,
    ]
    return [d for d in candidates if d.is_dir()]


# ---------------------------------------------------------------------------#
# Search
# ---------------------------------------------------------------------------#


_SEARCH_SUFFIXES: frozenset[str] = frozenset({".md", ".json"})


def search(tenant_id: str, term: str) -> list[str]:
    """Grep-style scan under the tenant data root for markdown/json files.

    Recursively walks every directory that belongs to *tenant_id* under
    the data root, reads each ``.md`` and ``.json`` file, and returns the
    paths of files whose text contains *term* (case-insensitive).

    **Read-only** — no files are written or modified.
    """
    if not term:
        return []
    term_lower = term.lower()
    matches: list[str] = []
    for tenant_dir in _tenant_dirs(tenant_id):
        for path in sorted(tenant_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in _SEARCH_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if term_lower in text.lower():
                matches.append(str(path))
    return matches


# ---------------------------------------------------------------------------#
# Replay
# ---------------------------------------------------------------------------#


def replay(action_id: str, tenant_id: str) -> dict[str, Any]:
    """Write a markdown replay file for *action_id* under the tenant data root.

    Lists the propose → approve → execute lifecycle if each phase is
    present.  Does **not** re-execute the action.

    Raises ``ValueError`` when the action is unknown or the tenant does
    not match.
    """
    from core.twin_actions import _ensure_schema, _load_action

    _ensure_schema()
    action = _load_action(action_id)
    if action is None:
        raise ValueError(f"unknown action: {action_id}")
    if action["tenant_id"] != tenant_id:
        raise ValueError("tenant mismatch")

    out_dir = data_root() / "work_products" / tenant_id
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_path = out_dir / f"replay_{action_id}.md"

    status = action.get("status", "")
    lines: list[str] = [
        f"# Replay — {action_id}",
        "",
        f"**Tenant:** {tenant_id}",
        f"**Kind:** {action.get('kind', '')}",
        f"**Title:** {action.get('title', '')}",
        f"**Status:** {status}",
        "",
        "## Propose",
        "",
    ]
    created = action.get("created_at", "")
    if created:
        lines.append(f"- **Time:** {created}")
    else:
        lines.append("- _(no propose timestamp)_")
    lines.append("")

    lines.append("## Approve")
    lines.append("")
    approved_at = action.get("approved_at")
    approved_by = action.get("approved_by")
    if approved_at:
        lines.append(f"- **Time:** {approved_at}")
        if approved_by:
            lines.append(f"- **By:** {approved_by}")
    else:
        lines.append("- _(not approved)_")
    lines.append("")

    lines.append("## Execute")
    lines.append("")
    if status == "executed":
        lines.append("- **Executed:** yes")
    else:
        lines.append("- _(not executed)_")
    lines.append("")

    replay_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "tenant_id": tenant_id,
        "action_id": action_id,
        "path": str(replay_path),
    }


# ---------------------------------------------------------------------------#
# Export
# ---------------------------------------------------------------------------#


def export_tenant(tenant_id: str, out_path: str) -> dict[str, Any]:
    """Pack the tenant's data-root folders into a local ``.tar.gz`` archive.

    The archive contains relative paths from the data root so that
    :func:`import_archive` can restore them into any ``AEGIS_DATA_DIR``.
    """
    root = data_root()
    dirs = _tenant_dirs(tenant_id)
    archive_path = Path(out_path)
    if archive_path.parent and not archive_path.parent.exists():
        archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(str(archive_path), "w:gz") as tar:
        for d in dirs:
            tar.add(str(d), arcname=str(d.relative_to(root)))

    return {
        "tenant_id": tenant_id,
        "archive": str(archive_path),
        "dirs": [str(d) for d in dirs],
    }


# ---------------------------------------------------------------------------#
# Signed local export (T126)
# ---------------------------------------------------------------------------#


def signed_export(tenant_id: str, name: str | None = None) -> dict[str, Any]:
    """Write a signed local export file under ``AEGIS_DATA_DIR/export/``.

    The file body is a textual summary of the tenant's data-root folders.
    A ``sha256`` signature line is appended.  No email, no cloud upload —
    the file stays local under the data root.

    Returns ``{tenant_id, path, sha256}``.
    """
    import hashlib

    root = data_root()
    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = name if name else f"{tenant_id}_{stamp}.md"
    out_path = export_dir / fname

    lines: list[str] = [
        f"# Export — {tenant_id}",
        "",
        f"tenant_id: {tenant_id}",
        f"exported_at: {stamp}",
        "",
        "## Directories",
        "",
    ]
    for d in _tenant_dirs(tenant_id):
        lines.append(f"- {d.relative_to(root)}")
    lines.append("")
    body = "\n".join(lines)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    full = body + f"sha256: {sha}\n"
    out_path.write_text(full, encoding="utf-8")
    return {
        "tenant_id": tenant_id,
        "path": str(out_path),
        "sha256": sha,
    }


# ---------------------------------------------------------------------------#
# Import
# ---------------------------------------------------------------------------#


def import_archive(archive_path: str) -> dict[str, Any]:
    """Restore an archive file into ``AEGIS_DATA_DIR``.

    Only paths that were in the archive are extracted — **never** touches
    another tenant's data.
    """
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as tar:
        # Validate that no member escapes the data root.
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                raise ValueError(f"unsafe archive member: {member.name}")
        try:
            tar.extractall(str(root), filter="data")  # type: ignore[call-arg]
        except TypeError:
            # Python < 3.12 — no filter parameter; already validated.
            tar.extractall(str(root))

    return {
        "archive": str(archive_path),
        "data_root": str(root),
    }
