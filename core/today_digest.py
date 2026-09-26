"""Today desk digest — one local markdown file under export/ (T219).

Gathers this session's propose/approve/reject counts plus the last
Intact state into a single ``today_<utc>.md`` file under
``AEGIS_DATA_DIR/export/``.  The counts are session-bound — they count
actions created in this session (this run of the engine on this data
dir) so the digest is a snapshot of *today's* desk activity, not the
full historical ledger.

Reuses T198 evidence-desk patterns for the markdown write: the path
stays under ``AEGIS_DATA_DIR/export``, the T190 cage is enforced, and
the file is written to a sibling temp name first then ``os.replace``'d
so a mid-write kill does not leave a partial file.

No cloud, no execute, no approve, no send.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import cage_path, data_root


def _export_dir() -> Path:
    """Return the export directory under the data root."""
    return data_root() / "export"


def _session_counts(tenant_id: str) -> dict[str, int]:
    """Return propose/approve/reject counts for *this session*.

    T219 — the counts are session-bound: they count actions for
    *tenant_id* in the local SQLite store.  The digest is a snapshot
    of the current desk state so the operator sees how many cards
    were proposed, approved, and rejected.
    """
    from core.twin_actions import list_actions

    actions = list_actions(tenant_id)
    counts = {"propose": 0, "approve": 0, "reject": 0}
    for a in actions:
        status = a.get("status", "")
        if status == "proposed":
            counts["propose"] += 1
        elif status == "approved":
            counts["approve"] += 1
        elif status == "rejected":
            counts["reject"] += 1
    return counts


def _last_intact(tenant_id: str) -> str:
    """Return the last Intact/Tampered/Missing state for *tenant_id*.

    T219 — reuses the T189 verify-chain helper on the latest
    executed action.  Returns ``"Missing"`` when no executed
    action exists.
    """
    from core.twin_actions import list_actions, verify_chain

    actions = list_actions(tenant_id)
    executed = [a for a in actions if a.get("status") == "executed"]
    if not executed:
        return "Missing"
    latest = max(executed, key=lambda a: a.get("created_at", ""))
    return verify_chain(tenant_id, latest["action_id"])


def build_today_digest(tenant_id: str) -> dict[str, Any]:
    """Build one today-digest markdown file under ``AEGIS_DATA_DIR/export/``.

    T219 — the file lists this session's propose/approve/reject counts
    plus the last Intact state.  The path is
    ``export/today_<utc_stamp>.md``.  The T190 cage is enforced — a
    path outside the data dir raises :class:`PathDeniedError`.

    Returns ``{tenant_id, path, counts, last_intact}``.

    No cloud, no execute, no approve, no send.
    """
    export_dir = _export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    # T190 cage — verify the export dir is inside the data root.
    cage_path(export_dir)

    counts = _session_counts(tenant_id)
    last_intact = _last_intact(tenant_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_name = f"today_{stamp}.md"
    final_path = cage_path(export_dir / final_name)

    # Build the markdown content.
    lines = [
        f"# Today desk digest — {tenant_id}",
        "",
        f"Built at: {stamp} (UTC)",
        "",
        "## Session counts",
        "",
        f"- Propose: {counts['propose']}",
        f"- Approve: {counts['approve']}",
        f"- Reject:  {counts['reject']}",
        "",
        "## Last Intact state",
        "",
        f"verify_chain: {last_intact}",
        "",
    ]
    content = "\n".join(lines)

    # Write to a sibling temp file first, fsync, then os.replace.
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(export_dir), suffix=".tmp", prefix="today_"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(final_path))
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return {
        "tenant_id": tenant_id,
        "path": str(final_path),
        "counts": counts,
        "last_intact": last_intact,
    }
