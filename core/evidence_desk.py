"""Local evidence desk — one tenant-bound evidence pack (T198).

Gathers this tenant's existing local proofs into a single
``evidence_YYYYMMDDThhmmssZ.zip`` under ``AEGIS_DATA_DIR/export/``.

Reuses, does not duplicate:

* T189 ``verify_chain`` — records ``Intact`` or ``Tampered`` for the
  most recent executed action as ``verify_chain.txt`` inside the pack.
* T126/T190 signed local brief — copies the newest ``local_*.md`` and
  its sibling ``.sig`` into the pack when they exist, or writes a
  typed ``missing_brief.txt`` note when no brief exists.
* T118 audit JSONL — copies only this tenant's tail (last 200 lines
  or last 64 KiB, whichever is smaller) after redacting
  bearer/webhook/SSH shapes with the T124/T190 redactor.
* T125 receipt hash prefixes — writes ``receipts.txt`` with the
  ``receipt_sha`` prefix from each receipt file for this tenant.
  No invented hashes.
* T190 ``cage_path`` — a destination outside ``AEGIS_DATA_DIR`` is a
  typed deny (``PathDeniedError``), not a silent skip.

The pack is written to a sibling temp name first, ``fsync``,
then ``os.replace`` so a mid-write kill does not leave a file the
operator page would treat as a finished pack.

Building the pack does not Approve, does not execute, does not
change queue membership, and does not import neighbor tenant data.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import cage_path, data_root

# Maximum tail size for the audit JSONL copy.
_MAX_AUDIT_LINES = 200
_MAX_AUDIT_BYTES = 64 * 1024  # 64 KiB


def _export_dir() -> Path:
    """Return the export directory under the data root."""
    return data_root() / "export"


def _newest_signed_brief() -> tuple[Path | None, Path | None]:
    """Return ``(brief_path, sig_path)`` for the newest ``local_*.md``
    under the export dir, or ``(None, None)`` when no brief exists.
    """
    export_dir = _export_dir()
    if not export_dir.is_dir():
        return None, None
    candidates = sorted(
        (p for p in export_dir.glob("local_*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None, None
    brief = candidates[-1]
    sig = brief.with_suffix(brief.suffix + ".sig")
    if not sig.is_file():
        sig = None  # type: ignore[assignment]
    return brief, sig


def _audit_tail(tenant_id: str) -> str:
    """Return the redacted tail of this tenant's audit JSONL.

    Reads every ``*.jsonl`` file under the audit dir, filters to
    events whose ``tenant_id`` extra matches *tenant_id* (or whose
    ``action_id`` belongs to a tenant action), takes the last 200
    lines or 64 KiB, and redacts secret shapes with the T124/T190
    redactor.
    """
    from core.redact import redact as _redact
    from core.twin_actions import list_actions

    root = data_root()
    audit_dir = root / "audit"
    if not audit_dir.is_dir():
        return ""

    # Collect action_ids that belong to this tenant so we can filter
    # audit events by correlation_id / action_id membership.
    actions = list_actions(tenant_id)
    tenant_action_ids = {a["action_id"] for a in actions}

    lines: list[str] = []
    for jsonl in sorted(audit_dir.glob("*.jsonl")):
        if not jsonl.is_file():
            continue
        for raw_line in jsonl.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            # Filter: the event's action_id belongs to this tenant.
            # Audit events carry an ``action_id`` field.
            import json as _json

            try:
                evt = _json.loads(stripped)
            except (ValueError, TypeError):
                continue
            eid = evt.get("action_id", "")
            if eid and eid in tenant_action_ids:
                lines.append(stripped)

    # Take the last N lines.
    tail = lines[-_MAX_AUDIT_LINES:] if lines else []
    tail_text = "\n".join(tail)
    # Truncate to _MAX_AUDIT_BYTES.
    if len(tail_text.encode("utf-8")) > _MAX_AUDIT_BYTES:
        tail_text = tail_text.encode("utf-8")[-_MAX_AUDIT_BYTES:].decode(
            "utf-8", errors="replace"
        )
    # Redact secret shapes.
    return _redact(tail_text)


def _receipt_hashes(tenant_id: str) -> list[str]:
    """Return ``receipt_sha`` prefixes for this tenant's receipts.

    Reads each ``*.md`` under
    ``work_products/{tenant_id}/receipts/`` and extracts the
    ``receipt_sha:`` value.  Returns a list of 12-character prefixes.
    No invented hashes.
    """
    root = data_root()
    receipts_dir = root / "work_products" / tenant_id / "receipts"
    if not receipts_dir.is_dir():
        return []
    hashes: list[str] = []
    for md in sorted(receipts_dir.glob("*.md")):
        if not md.is_file():
            continue
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("receipt_sha:"):
                sha = line.split("receipt_sha:", 1)[1].strip()
                if sha:
                    hashes.append(sha[:12])
                break
    return hashes


def _verify_chain_result(tenant_id: str) -> tuple[str, str]:
    """Return ``(action_id, result)`` from the T189 verify_chain helper.

    Reuses the verify-chain route logic: finds the latest executed
    action for the tenant and verifies its receipt chain.  Returns
    ``("", "Missing")`` when no executed action exists.
    """
    from core.twin_actions import list_actions, verify_chain

    actions = list_actions(tenant_id)
    executed = [a for a in actions if a.get("status") == "executed"]
    if not executed:
        return "", "Missing"
    latest = max(executed, key=lambda a: a.get("created_at", ""))
    action_id = latest["action_id"]
    return action_id, verify_chain(tenant_id, action_id)


def build_evidence_pack(tenant_id: str) -> dict[str, Any]:
    """Build one tenant-bound evidence pack under ``AEGIS_DATA_DIR/export/``.

    Returns ``{tenant_id, path, sha256}`` where ``path`` is the zip
    path and ``sha256`` is the hex digest of the zip bytes.

    The pack is written to a sibling temp name first, ``fsync``,
    then ``os.replace`` so a mid-write kill does not leave a file
    the operator page would treat as a finished pack.

    Raises :class:`PathDeniedError` when the export dir resolves
    outside ``AEGIS_DATA_DIR``.
    """
    import tempfile

    export_dir = _export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    # T190 cage — verify the export dir is inside the data root.
    cage_path(export_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_name = f"evidence_{stamp}.zip"
    final_path = cage_path(export_dir / final_name)

    # Build the pack contents in memory first, then write atomically.
    # 1) verify_chain result
    vc_action_id, vc_result = _verify_chain_result(tenant_id)
    vc_text = (
        f"verify_chain: {vc_result}\n"
        f"action_id: {vc_action_id}\n"
        f"tenant_id: {tenant_id}\n"
    )

    # 2) signed brief + .sig
    brief_path, sig_path = _newest_signed_brief()
    brief_content: str | None = None
    sig_content: str | None = None
    brief_verify: str = "Missing"
    if brief_path is not None and brief_path.is_file():
        brief_content = brief_path.read_text(encoding="utf-8")
        if sig_path is not None and sig_path.is_file():
            sig_content = sig_path.read_text(encoding="utf-8")
        # T204 — local verifier result for the brief+.sig pair.
        from core.twin_local_recall import verify_local_sig

        brief_verify = verify_local_sig(str(brief_path))

    # 3) audit tail (redacted)
    audit_text = _audit_tail(tenant_id)

    # 4) receipt hashes
    r_hashes = _receipt_hashes(tenant_id)
    receipts_text = "\n".join(r_hashes) + ("\n" if r_hashes else "")

    # Write to a sibling temp file first, fsync, then os.replace.
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(export_dir), suffix=".tmp", prefix="evidence_"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("verify_chain.txt", vc_text)
                if brief_content is not None:
                    zf.writestr("brief.md", brief_content)
                    if sig_content is not None:
                        zf.writestr("brief.md.sig", sig_content)
                else:
                    zf.writestr(
                        "missing_brief.txt",
                        "missing_brief: no signed local brief found\n",
                    )
                # T204 — local brief verify result (Intact/Tampered/Missing).
                zf.writestr("brief_verify.txt", brief_verify + "\n")
                zf.writestr("audit_tail.jsonl", audit_text + "\n")
                zf.writestr("receipts.txt", receipts_text)
                # Manifest with the tenant id and timestamp.
                zf.writestr(
                    "manifest.txt",
                    f"tenant_id: {tenant_id}\n"
                    f"built_at: {stamp}\n",
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(final_path))
    except BaseException:
        # Clean up the temp file on any failure.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    sha = hashlib.sha256(final_path.read_bytes()).hexdigest()
    return {
        "tenant_id": tenant_id,
        "path": str(final_path),
        "sha256": sha,
    }
