"""Local purchase receipt — one JSON file per tenant under AEGIS_DATA_DIR.

T229 — a local purchase receipt can be stored and later cited by one Approve
on the same tenant.  The receipt is a citation only: it does **not** unlock
execute, does **not** flip status, and does **not** call a card network.

Fields:
    tenant_id   — string identifying the tenant this receipt is bound to
    receipt_id  — a stable id for this receipt
    issued_at   — ISO-8601 UTC string
    plan_label  — a short label (e.g. ``"professional"``)
    status      — ``"paid_local"`` or ``"void"``
    sha256      — SHA-256 hex digest of the canonical receipt bytes
                  (every field **except** ``sha256``, serialised with
                  ``sort_keys=True, separators=(",", ":")``)

Cross-tenant read of the receipt returns a typed deny (``receipt_deny``).
A void receipt stays void.  Expiry and cancel from T228 do not clear the
local receipt file by themselves — they stay Echo-limited in the
entitlement layer, not here.

No card network, no webhook in core.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _receipts_dir() -> Path:
    """Return the purchase-receipts directory under AEGIS_DATA_DIR."""
    from core.twin_local_view import cage_path, data_root

    root = data_root()
    rdir = root / "purchase_receipts"
    rdir = cage_path(rdir)
    rdir.mkdir(parents=True, exist_ok=True)
    return rdir


def _receipt_path(tenant_id: str) -> Path:
    """Return the path to the purchase-receipt JSON for *tenant_id*."""
    return _receipts_dir() / f"receipt_{tenant_id}.json"


def _canonical_body(data: dict[str, Any]) -> str:
    """Return the canonical JSON of *data* without the ``sha256`` field."""
    body = {k: v for k, v in data.items() if k != "sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _signature_valid(data: dict[str, Any]) -> bool:
    """Return True when ``sha256`` matches the canonical body."""
    sig = data.get("sha256")
    if not isinstance(sig, str) or not sig:
        return False
    body = _canonical_body(data)
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return sig == expected


def write_purchase_receipt(
    tenant_id: str,
    receipt_id: str,
    plan_label: str = "",
    status: str = "paid_local",
) -> Path:
    """Write one local purchase-receipt JSON under ``AEGIS_DATA_DIR``.

    The receipt is a citation record — it does **not** unlock execute,
    does **not** call a card network, and does **not** flip any action
    status.  ``status`` is ``"paid_local"`` or ``"void"``.

    Returns the path to the written receipt file.
    """
    from core.twin_local_view import cage_path

    path = _receipt_path(tenant_id)
    path = cage_path(path)
    now = datetime.now(timezone.utc).isoformat()
    data: dict[str, Any] = {
        "tenant_id": tenant_id,
        "receipt_id": receipt_id,
        "issued_at": now,
        "plan_label": plan_label,
        "status": status,
    }
    canonical = _canonical_body(data)
    data["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def read_purchase_receipt(tenant_id: str) -> dict[str, Any]:
    """Read the local purchase receipt for *tenant_id*.

    Returns a dict with:
        found        — True when a valid receipt exists for this tenant
        receipt_id   — the receipt id (or ``""`` when not found)
        status       — ``"paid_local"``, ``"void"``, or ``"missing"``
        sha256       — the receipt's sha256 (or ``""``)
        deny_reason  — ``""`` when same-tenant, ``"receipt_deny"`` when
                        a different tenant's receipt was requested

    Cross-tenant read returns ``found=False`` with
    ``deny_reason="receipt_deny"`` — never the neighbour's receipt body.
    A missing file returns ``found=False`` with ``status="missing"``.
    A void receipt stays void (``status="void"``).

    The receipt does not unlock execute and does not block Approve.
    """
    path = _receipt_path(tenant_id)
    if not path.is_file():
        return {
            "found": False,
            "receipt_id": "",
            "status": "missing",
            "sha256": "",
            "deny_reason": "",
        }
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return {
            "found": False,
            "receipt_id": "",
            "status": "missing",
            "sha256": "",
            "deny_reason": "",
        }
    if not isinstance(data, dict):
        return {
            "found": False,
            "receipt_id": "",
            "status": "missing",
            "sha256": "",
            "deny_reason": "",
        }
    # Cross-tenant guard: the file's tenant_id must match.
    file_tenant = data.get("tenant_id")
    if not isinstance(file_tenant, str) or file_tenant != tenant_id:
        return {
            "found": False,
            "receipt_id": "",
            "status": "missing",
            "sha256": "",
            "deny_reason": "receipt_deny",
        }
    # Signature check.
    if not _signature_valid(data):
        return {
            "found": False,
            "receipt_id": "",
            "status": "missing",
            "sha256": "",
            "deny_reason": "receipt_deny",
        }
    return {
        "found": True,
        "receipt_id": data.get("receipt_id", ""),
        "status": data.get("status", "paid_local"),
        "sha256": data.get("sha256", ""),
        "deny_reason": "",
    }


def void_purchase_receipt(tenant_id: str) -> dict[str, Any]:
    """Void the purchase receipt for *tenant_id*.

    Sets ``status`` to ``"void"`` and re-signs the file.  A void
    receipt stays void — it is not cleared by expiry or cancel from
    the T228 entitlement layer.
    """
    path = _receipt_path(tenant_id)
    if not path.is_file():
        return {
            "found": False,
            "status": "missing",
        }
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return {
            "found": False,
            "status": "missing",
        }
    if not isinstance(data, dict):
        return {
            "found": False,
            "status": "missing",
        }
    data["status"] = "void"
    canonical = _canonical_body(data)
    data["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "found": True,
        "status": "void",
        "receipt_id": data.get("receipt_id", ""),
        "sha256": data.get("sha256", ""),
    }
