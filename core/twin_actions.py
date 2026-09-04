"""Twin proposed actions with human approval gate (T06).

The twin may *propose* work items derived from the consented profile and
weekly digest, but it must not act until the human approves.  Execution for
this slice is a stub that records ``"executed"`` in SQLite only — no external
side effects.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_interview import get_latest_profile
from core.twin_risk import attach_risk, classify

# ---------------------------------------------------------------------------#
# Constants
# ---------------------------------------------------------------------------#

ACTION_KINDS: tuple[str, ...] = (
    "review_digest",
    "review_repos",
    "prepare_weekly_plan",
)

_VALID_STATUSES: frozenset[str] = frozenset(
    {"proposed", "approved", "rejected", "executed"}
)

_action_lock = threading.Lock()

_POLICY_VERSION = "t56"


# ---------------------------------------------------------------------------#
# Canonical envelope & digest (T56)
# ---------------------------------------------------------------------------#

def _canonical_envelope(
    action_id: str,
    tenant_id: str,
    kind: str,
    title: str,
    payload: Any,
    effect_type: str | None,
    risk_level: str,
    policy_version: str = _POLICY_VERSION,
) -> dict[str, Any]:
    """Build the canonical, sorted-key envelope dict for an action.

    ``effect_type`` defaults to ``kind`` when no separate field is present.
    ``risk_level`` defaults to ``""`` when absent.  ``policy_version`` is
    always ``"t56"``.
    """
    return {
        "action_id": action_id,
        "tenant_id": tenant_id,
        "kind": kind,
        "title": title,
        "payload": payload,
        "effect_type": effect_type if effect_type is not None else kind,
        "risk_level": risk_level if risk_level else "",
        "policy_version": policy_version,
    }


def _envelope_digest(envelope: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of the canonical JSON envelope."""
    serialized = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _action_digest(action: dict[str, Any]) -> str:
    """Compute the canonical envelope digest from an action dict."""
    payload = action.get("payload")
    effect_type = action.get("effect_type")
    risk_level = action.get("risk_level", "")
    if not risk_level:
        risk_level = classify(action.get("title", ""))
    envelope = _canonical_envelope(
        action_id=action["action_id"],
        tenant_id=action["tenant_id"],
        kind=action["kind"],
        title=action["title"],
        payload=payload,
        effect_type=effect_type,
        risk_level=risk_level,
    )
    return _envelope_digest(envelope)


# ---------------------------------------------------------------------------#
# Schema
# ---------------------------------------------------------------------------#

def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_actions (
                action_id   TEXT PRIMARY KEY,
                tenant_id   TEXT    NOT NULL,
                kind        TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                payload     TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_twin_actions_tenant
            ON twin_actions (tenant_id)
            """
        )
        # Add payload column to pre-T49 tables (best-effort).
        for col in ("payload",):
            try:
                conn.execute(f"ALTER TABLE twin_actions ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        # T56 — approval binding columns.
        for col in (
            "payload_sha256 TEXT",
            "approved_payload_sha256 TEXT",
            "approved_by TEXT",
            "approved_at TEXT",
        ):
            try:
                conn.execute(f"ALTER TABLE twin_actions ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass


# ---------------------------------------------------------------------------#
# Internal helpers
# ---------------------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row (or dict) into a plain action dict."""
    if isinstance(row, dict):
        return dict(row)
    keys = row.keys()
    result: dict[str, Any] = {
        "action_id": row["action_id"],
        "tenant_id": row["tenant_id"],
        "kind": row["kind"],
        "title": row["title"],
        "status": row["status"],
        "created_at": row["created_at"],
        "payload": _deserialize_payload(row["payload"]) if "payload" in keys else None,
    }
    # T56 optional columns.
    if "payload_sha256" in keys:
        result["payload_sha256"] = row["payload_sha256"]
    if "approved_payload_sha256" in keys:
        result["approved_payload_sha256"] = row["approved_payload_sha256"]
    if "approved_by" in keys:
        result["approved_by"] = row["approved_by"]
    if "approved_at" in keys:
        result["approved_at"] = row["approved_at"]
    return result


def _deserialize_payload(raw: str | None) -> Any:
    """Deserialize a JSON payload from the DB, or return the raw str."""
    import json

    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _load_action(action_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT action_id, tenant_id, kind, title, status, created_at, "
            "payload, payload_sha256, approved_payload_sha256, approved_by, approved_at "
            "FROM twin_actions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def _update_status(action_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE twin_actions SET status = ? WHERE action_id = ?",
            (status, action_id),
        )


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def propose_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Deterministically propose work items for ``tenant_id``.

    Requires a consented profile (otherwise ``ValueError`` is raised).
    Returns at least one ``review_digest`` action; additionally
    ``review_repos`` if the profile has non-empty repositories, and
    always ``prepare_weekly_plan``.
    """
    _ensure_schema()
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    actions: list[dict[str, Any]] = []
    now = _now()

    # 1. Always propose review_digest.
    actions.append(
        attach_risk(
            {
                "action_id": f"act-{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "kind": "review_digest",
                "title": "Review weekly digest",
                "status": "proposed",
                "created_at": now,
            }
        )
    )

    # 2. Propose review_repos if the profile has repositories.
    repos_raw = profile.get("repositories", "") or ""
    repos = [r.strip() for r in repos_raw.split(",") if r.strip()] if repos_raw else []
    if repos:
        actions.append(
            attach_risk(
                {
                    "action_id": f"act-{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "kind": "review_repos",
                    "title": f"Review repositories: {', '.join(repos)}",
                    "status": "proposed",
                    "created_at": now,
                }
            )
        )

    # 3. Always propose prepare_weekly_plan.
    actions.append(
        attach_risk(
            {
                "action_id": f"act-{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "kind": "prepare_weekly_plan",
                "title": "Prepare weekly plan",
                "status": "proposed",
                "created_at": now,
            }
        )
    )

    # Persist.
    with _action_lock:
        with get_connection() as conn:
            for a in actions:
                # Compute the canonical envelope digest for this action.
                payload_val = a.get("_payload_json")
                payload_for_digest = (
                    json.loads(payload_val) if isinstance(payload_val, str) else payload_val
                )
                risk_level = a.get("risk_level", "")
                if not risk_level:
                    risk_level = classify(a.get("title", ""))
                envelope = _canonical_envelope(
                    action_id=a["action_id"],
                    tenant_id=a["tenant_id"],
                    kind=a["kind"],
                    title=a["title"],
                    payload=payload_for_digest,
                    effect_type=a.get("effect_type"),
                    risk_level=risk_level,
                )
                digest = _envelope_digest(envelope)
                conn.execute(
                    "INSERT INTO twin_actions "
                    "(action_id, tenant_id, kind, title, status, "
                    "created_at, payload, payload_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        a["action_id"],
                        a["tenant_id"],
                        a["kind"],
                        a["title"],
                        a["status"],
                        a["created_at"],
                        a.get("_payload_json"),
                        digest,
                    ),
                )

    return actions


def approve(
    action_id: str,
    tenant_id: str | None = None,
    actor_id: str | None = None,
    expected_payload_sha256: str | None = None,
) -> dict[str, Any]:
    """Approve a proposed action after binding it to the exact envelope digest.

    All four arguments after ``action_id`` are required — calling with only
    ``action_id`` raises ``ValueError("digest required")``.

    Within one transaction:
    1. The row must exist.
    2. ``tenant_id`` must match.
    3. ``status`` must be ``proposed``.
    4. ``expected_payload_sha256`` must equal the current envelope digest.

    On success, sets ``approved_payload_sha256``, ``approved_by``,
    ``approved_at`` and ``status = "approved"``.
    """
    if expected_payload_sha256 is None:
        raise ValueError("digest required")

    _ensure_schema()
    with _action_lock:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT action_id, tenant_id, kind, title, status, created_at, "
                "payload, payload_sha256, approved_payload_sha256, approved_by, approved_at "
                "FROM twin_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown action: {action_id}")
            if row["tenant_id"] != tenant_id:
                raise ValueError("tenant mismatch")
            if row["status"] != "proposed":
                raise ValueError(
                    f"action not proposed (current status: {row['status']})"
                )
            # Recompute the current digest from the stored row.
            action_dict = _row_to_dict(row)
            current_digest = _action_digest(action_dict)
            if expected_payload_sha256 != current_digest:
                raise ValueError("payload digest mismatch")
            now = _now()
            conn.execute(
                "UPDATE twin_actions "
                "SET status = 'approved', "
                "    approved_payload_sha256 = ?, "
                "    approved_by = ?, "
                "    approved_at = ? "
                "WHERE action_id = ?",
                (expected_payload_sha256, actor_id, now, action_id),
            )
            action_dict["status"] = "approved"
            action_dict["approved_payload_sha256"] = expected_payload_sha256
            action_dict["approved_by"] = actor_id
            action_dict["approved_at"] = now
            return action_dict


def reject(action_id: str, tenant_id: str | None = None) -> dict[str, Any]:
    """Set an action's status to ``rejected``.

    If ``tenant_id`` is provided, the action's ``tenant_id`` must match or
    ``ValueError("tenant mismatch")`` is raised.  Raises ``ValueError`` if
    the action_id is unknown.
    """
    _ensure_schema()
    with _action_lock:
        action = _load_action(action_id)
        if action is None:
            raise ValueError(f"unknown action: {action_id}")
        if tenant_id is not None and action["tenant_id"] != tenant_id:
            raise ValueError("tenant mismatch")
        _update_status(action_id, "rejected")
        action["status"] = "rejected"
        return action


def _work_products_dir(tenant_id: str) -> Path:
    """Return the work-products base directory for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _is_email_action(action: dict[str, Any]) -> bool:
    """Return True if the action's title or kind mentions email."""
    haystack = f"{action.get('kind', '')} {action.get('title', '')}".lower()
    return "email" in haystack


def _write_receipt(action: dict[str, Any]) -> Path:
    """Write ``work_products/{tenant_id}/receipts/{action_id}.md``.

    One file per *action_id*.  Returns the path of the written receipt.
    """
    tenant_id = action["tenant_id"]
    action_id = action["action_id"]
    receipts_dir = _work_products_dir(tenant_id) / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    md_path = receipts_dir / f"{action_id}.md"
    lines = [
        f"action_id: {action_id}",
        f"title: {action['title']}",
        f"kind: {action['kind']}",
        f"tenant_id: {tenant_id}",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def execute(action_id: str, tenant_id: str | None = None) -> dict[str, Any]:
    """Execute an approved action.

    The local receipt (or outbox ``.eml`` for email actions) must exist on
    disk *before* the SQLite status becomes ``executed``.  If the write
    raises, status stays ``approved``.

    If ``tenant_id`` is provided, the action's ``tenant_id`` must match or
    ``ValueError("tenant mismatch")`` is raised.  Raises
    ``PermissionError("approval required")`` if the action is not in the
    ``approved`` status.  Raises ``ValueError`` if the action_id is unknown.

    A second execute of an already-executed id raises ``ValueError`` instead
    of rewriting a second receipt as success.
    """
    _ensure_schema()
    with _action_lock:
        action = _load_action(action_id)
        if action is None:
            raise ValueError(f"unknown action: {action_id}")
        if tenant_id is not None and action["tenant_id"] != tenant_id:
            raise ValueError("tenant mismatch")
        if action["status"] == "executed":
            raise ValueError("action already executed")
        if action["status"] != "approved":
            raise PermissionError("approval required")
        # T56 — recompute the current envelope digest and compare to the
        # approved_payload_sha256 captured at approve time.  Mismatch means
        # the payload was mutated after approval.
        current_digest = _action_digest(action)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT approved_payload_sha256 FROM twin_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        approved_digest = row["approved_payload_sha256"] if row else None
        if approved_digest is None or current_digest != approved_digest:
            raise ValueError("payload changed after approval")

        # Write the local receipts/ file (or outbox .eml for email actions)
        # while status is still ``approved``.  If this raises, status must
        # NOT change to ``executed``.
        if _is_email_action(action):
            from core.twin_email_send import send_approved

            send_approved(action["tenant_id"], action_id)
        else:
            _write_receipt(action)

        # Only now flip status to executed inside the same lock.
        _update_status(action_id, "executed")
        action["status"] = "executed"

    # Write evidence ledger entry (best-effort; do not fail if ledger is broken).
    try:
        from core.evidence_ledger import EvidenceLedgerSingleton

        EvidenceLedgerSingleton.append_entry(
            tenant_id=action["tenant_id"],
            actor="twin",
            action="twin_action_executed",
            payload={"action_id": action_id, "kind": action["kind"]},
        )
    except Exception:
        pass

    return action


def list_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Return all actions for ``tenant_id`` ordered by ``created_at``."""
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT action_id, tenant_id, kind, title, status, created_at, "
            "payload, payload_sha256, approved_payload_sha256, approved_by, approved_at "
            "FROM twin_actions WHERE tenant_id = ? "
            "ORDER BY created_at ASC",
            (tenant_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
