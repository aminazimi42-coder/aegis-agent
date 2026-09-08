"""Local deterministic feedback stats and confidence scoring (T117).

Computes a moving approval rate per ``(specialist, effect_type)`` pair from
the durable ``twin_feedback`` rows and their linked ``twin_actions`` rows.
The approval rate is a **confidence label only** — it never drops or
auto-executes a proposed action.  When the rate is low, a warning flag is
attached to the next proposal for that pair; the row stays in the queue
for a human to approve or reject.

No live network.  All data comes from the local SQLite database via
:func:`core.persistence.get_connection`.
"""

from __future__ import annotations

from typing import Any

from core.persistence import get_connection

# ---------------------------------------------------------------------------#
# Schema helpers
# ---------------------------------------------------------------------------#

def _ensure_schema() -> None:
    """Ensure the ``twin_feedback`` and ``twin_actions`` tables exist."""
    from core.twin_actions import _ensure_schema as _ta_schema

    _ta_schema()


def _feedback_rows() -> list[dict[str, Any]]:
    """Return all ``twin_feedback`` rows joined to ``twin_actions``."""
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT f.action_id, f.tenant_id, f.decision, "
            "       a.kind, a.effect_type, a.payload "
            "FROM twin_feedback AS f "
            "LEFT JOIN twin_actions AS a ON f.action_id = a.action_id ",
        ).fetchall()
    return [
        {
            "action_id": r["action_id"],
            "tenant_id": r["tenant_id"],
            "decision": r["decision"],
            "kind": r["kind"],
            "effect_type": r["effect_type"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def approval_rate(tenant_id: str, specialist: str, effect_type: str) -> float:
    """Return the moving approval rate for *tenant_id* / *specialist* / *effect_type*.

    The rate is ``approves / (approves + rejects)`` over the feedback rows
    whose action ``kind`` starts with ``f"{specialist}:"`` (or whose
    ``effect_type`` matches when ``kind`` does not carry a prefix) and
    whose ``effect_type`` matches *effect_type*.  Returns ``1.0`` when
    there is no feedback yet (no evidence of problems).
    """
    _ensure_schema()
    kind_prefix = f"{specialist}:"
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT f.decision FROM twin_feedback AS f "
            "JOIN twin_actions AS a ON f.action_id = a.action_id "
            "WHERE f.tenant_id = ? AND a.kind LIKE ?",
            (tenant_id, kind_prefix + "%"),
        ).fetchall()
    approves = 0
    rejects = 0
    for r in rows:
        if r["decision"] == "approve":
            approves += 1
        elif r["decision"] == "reject":
            rejects += 1
    total = approves + rejects
    if total == 0:
        return 1.0
    return approves / total


def confidence_score(tenant_id: str, specialist: str, effect_type: str) -> float:
    """Return a confidence label in ``[0.0, 1.0]`` for the next proposal.

    The confidence label is the moving approval rate for the pair.  It is
    a **label only** — it never drops the row or blocks the propose.
    """
    return approval_rate(tenant_id, specialist, effect_type)


def is_low_confidence(score: float, *, threshold: float = 0.5) -> bool:
    """Return True when *score* is below the *threshold* (default 0.5)."""
    return score < threshold


def attach_confidence(
    tenant_id: str,
    action: dict[str, Any],
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Attach ``confidence_score`` and ``low_confidence_warning`` to *action*.

    Derives ``(specialist, effect_type)`` from the action's ``kind`` /
    ``effect_type`` fields.  Never drops or blocks the action — only
    annotates it.
    """
    kind = action.get("kind", "")
    effect = action.get("effect_type") or kind
    specialist = kind.split(":")[0] if ":" in kind else kind
    score = confidence_score(tenant_id, specialist, effect)
    action["confidence_score"] = round(score, 4)
    action["low_confidence_warning"] = is_low_confidence(score, threshold=threshold)
    return action
