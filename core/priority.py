"""Deterministic queue priority for proposed twin_actions (T117).

The queue order is a transparent linear score:

    score = w_risk * risk_level + w_age * age_hours + w_specialist * specialist_weight

Higher score = higher priority (appears earlier in the queue).

The home/list of proposed ``twin_actions`` uses this order.  This does not
create a second queue — it sorts the existing ``twin_actions`` rows.

No live network.  All weights come from :mod:`core.priority_weights` or the
local ``core/priority_weights.py`` constants file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from core.priority_weights import (
    RISK_NUMERIC,
    SPECIALIST_WEIGHTS,
    W_AGE,
    W_RISK,
    W_SPECIALIST,
)
from core.twin_risk import classify


def _weights() -> tuple[float, float, float]:
    """Return (w_risk, w_age, w_specialist) honouring env overrides."""
    w_risk = W_RISK
    w_age = W_AGE
    w_specialist = W_SPECIALIST
    try:
        w_risk = float(os.getenv("AEGIS_PRIORITY_W_RISK", str(W_RISK)))
    except (TypeError, ValueError):
        pass
    try:
        w_age = float(os.getenv("AEGIS_PRIORITY_W_AGE", str(W_AGE)))
    except (TypeError, ValueError):
        pass
    try:
        w_specialist = float(
            os.getenv("AEGIS_PRIORITY_W_SPECIALIST", str(W_SPECIALIST))
        )
    except (TypeError, ValueError):
        pass
    return w_risk, w_age, w_specialist


def _specialist_weight(kind: str) -> float:
    """Return the per-specialist weight derived from *kind*."""
    specialist = kind.split(":")[0] if ":" in kind else kind
    return SPECIALIST_WEIGHTS.get(specialist, 1.0)


def _risk_numeric(action: dict[str, Any]) -> float:
    """Return the numeric risk level for *action*."""
    risk = action.get("risk_level") or ""
    if risk in RISK_NUMERIC:
        return RISK_NUMERIC[risk]
    effect = action.get("effect_type") or action.get("kind") or ""
    return RISK_NUMERIC.get(classify(action.get("title", ""), effect), 0.0)


def _age_hours(action: dict[str, Any]) -> float:
    """Return the age of *action* in hours from ``created_at``."""
    created = action.get("created_at") or ""
    if not created:
        return 0.0
    try:
        dt = datetime.fromisoformat(created)
    except (ValueError, TypeError):
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return max(delta.total_seconds() / 3600.0, 0.0)


def action_score(action: dict[str, Any]) -> float:
    """Return the priority score for a single *action*.

    ``score = w_risk * risk_level + w_age * age_hours + w_specialist * specialist_weight``
    """
    w_risk, w_age, w_specialist = _weights()
    risk = _risk_numeric(action)
    age = _age_hours(action)
    kind = action.get("kind", "")
    sw = _specialist_weight(kind)
    return w_risk * risk + w_age * age + w_specialist * sw


def sort_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *actions* sorted by descending priority score (highest first).

    The sort is stable so actions with equal scores retain their original
    relative order.
    """
    return sorted(actions, key=action_score, reverse=True)


def prioritize_pending(tenant_id: str) -> list[dict[str, Any]]:
    """Return the proposed actions for *tenant_id* sorted by priority.

    Reads ``twin_actions`` via :func:`core.twin_actions.list_actions` and
    returns only rows whose status is ``proposed``, sorted by descending
    priority score.  Does not create a second queue.
    """
    from core.twin_actions import list_actions

    pending = [a for a in list_actions(tenant_id) if a.get("status") == "proposed"]
    return sort_actions(pending)
