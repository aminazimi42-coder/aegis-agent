"""Action risk-level classification (T43).

Every proposed action carries a risk level so the human gatekeeper knows
which items are safe to leave as ``proposed`` and which require explicit
approval before any side-effect occurs.

Risk levels (low → high):

- ``L0`` — observe only; no side effects.
- ``L1`` — drafting / planning; local artifacts only.
- ``L2`` — writes, commits, pushes, emails — side effects that change state.
- ``L3`` — payments, deployments, account deletions — irreversible external
  side effects that **always** require human approval.

No action is auto-approved or auto-executed; ``classify`` is a pure
function that maps a title string to a risk-level string.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------#
# Keyword tables (lower-case substrings)
# ---------------------------------------------------------------------------#

_L3_KEYWORDS: tuple[str, ...] = (
    "pay",
    "wire",
    "deploy",
    "production",
    "delete account",
)

_L2_KEYWORDS: tuple[str, ...] = (
    "email",
    "send",
    "push",
    "commit",
    "write",
    "invoice",
)

_L1_KEYWORDS: tuple[str, ...] = (
    "draft",
    "plan",
    "brief",
    "summary",
)

_RISK_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def classify(title: str) -> str:
    """Classify *title* into a risk level (``L0``–``L3``).

    Higher-risk keywords take precedence over lower-risk ones.  The
    comparison is case-insensitive and based on substring containment.
    """
    t = (title or "").lower()

    # L3 — irreversible / external.
    for kw in _L3_KEYWORDS:
        if kw in t:
            return "L3"

    # L2 — state-changing side effects.
    for kw in _L2_KEYWORDS:
        if kw in t:
            return "L2"

    # L1 — drafting / planning (local artifacts).
    for kw in _L1_KEYWORDS:
        if kw in t:
            return "L1"

    # Default — observe only.
    return "L0"


def attach_risk(action: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *action* with ``risk_level`` set via :func:`classify`.

    If ``risk_level`` is already present it is recomputed from the title
    so the field always reflects the canonical classification.
    """
    result = dict(action)
    result["risk_level"] = classify(result.get("title", ""))
    return result
