"""Typed tenant switch — confirm-word gate (T208).

A typed tenant switch: the operator enters the target tenant id and the
exact confirm word ``SWITCH_TENANT``.  A wrong confirm word is a typed
deny ``TENANT_SWITCH_CONFIRM_REQUIRED`` — no switch.

After a valid switch, ``list_queue``, the Approved strip, and
``GET /api/v1/twin/profile/<id>`` return only the target tenant.  Source
tenant cards stay on the source tenant; neighbor queues do not merge.

The switch sets the durable last-tenant marker (T119) so a new process
reads the target tenant as the active one.  No queue merge, no action
copy across tenants.
"""

from __future__ import annotations

CONFIRM_WORD = "SWITCH_TENANT"
DENY_CODE = "TENANT_SWITCH_CONFIRM_REQUIRED"


def switch_tenant(target_tenant_id: str, confirm: str) -> dict[str, str]:
    """Switch to *target_tenant_id* when *confirm* matches the exact word.

    Returns ``{"tenant_id": target, "switched": "true", "code": "tenant_switched"}``
    on success, or ``{"tenant_id": target, "switched": "false",
    "code": "TENANT_SWITCH_CONFIRM_REQUIRED"}`` when the confirm word
    does not match.  No switch on a wrong confirm — the current tenant
    is unchanged.

    The target tenant id must be non-empty; an empty id is also a typed
    deny with the same code.
    """
    from core.twin_interview import get_last_tenant, set_last_tenant

    target = (target_tenant_id or "").strip()
    if not target or confirm != CONFIRM_WORD:
        return {
            "tenant_id": target,
            "switched": "false",
            "code": DENY_CODE,
        }
    set_last_tenant(target)
    return {
        "tenant_id": target,
        "switched": "true",
        "code": "tenant_switched",
        "previous": get_last_tenant() or "",
    }
