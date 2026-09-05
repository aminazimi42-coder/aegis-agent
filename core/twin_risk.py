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
# L0 allow-list (T63)
# ---------------------------------------------------------------------------#
#
# Only an explicit, local allow-list of effect/kind strings may be classified
# as ``L0`` (observe-only, no side effects).  Any effect not in this set is at
# least ``L1`` and therefore requires human scrutiny before it can execute.
#
# The set contains **only** effects that already exist in the codebase and are
# purely local / observational:
#
# - ``"file observe"`` — reading local files (twin_file_observer concept)
# - ``"git observe"``  — local ``git log`` scanning (twin_git_observer)
# - ``"local .eml outbox"`` — writing an ``.eml`` to the local outbox only
# - ``"review_digest"`` — propose a review-digest action (T06)
# - ``"review_repos"`` — propose a review-repos action (T06)
# - ``"prepare_weekly_plan"`` — propose a weekly-plan action (T06)
# - Specialist propose kinds follow ``"{agent_name}:propose"`` (T60).  The
#   allow-list therefore also includes the bare ``"propose"`` suffix so that
#   any ``*:propose`` kind is recognised as a known local effect.

ALLOWED_L0_EFFECTS: frozenset[str] = frozenset(
    {
        "file observe",
        "git observe",
        "local .eml outbox",
        "review_digest",
        "review_repos",
        "prepare_weekly_plan",
        "propose",
    }
)


def _is_allowed_l0_effect(effect: str) -> bool:
    """Return True if *effect* is an explicitly allowed L0 effect.

    Specialist proposal kinds (``"{agent_name}:propose"``) are allowed when
    the suffix ``"propose"`` matches.
    """
    if not effect:
        return False
    if effect in ALLOWED_L0_EFFECTS:
        return True
    # ``"Alina:propose"`` → suffix ``"propose"``.
    if ":" in effect:
        suffix = effect.rsplit(":", 1)[-1]
        return suffix in ALLOWED_L0_EFFECTS
    return False


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def classify(title: str, effect: str | None = None) -> str:
    """Classify *title* (optionally qualified by *effect*) into a risk level.

    Higher-risk keywords take precedence over lower-risk ones.  The
    comparison is case-insensitive and based on substring containment.

    **T63 — L0 allow-list:**  When *effect* is supplied and is not in
    :data:`ALLOWED_L0_EFFECTS`, the result is at least ``L1`` — an unknown
    effect can never be ``L0`` even if the title contains no risky keywords.
    When *effect* is ``None`` the legacy title-only behaviour is preserved
    so existing callers (``plan_goal``, ``attach_risk`` without an effect,
    etc.) continue to work unchanged.
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

    # T63 — if an effect was supplied and is on the L0 allow-list, the
    # action may be L0 even if the title contains L1 keywords (``plan``,
    # ``draft``, …).  Known local effects are trusted to be side-effect
    # free.
    if effect is not None and _is_allowed_l0_effect(effect):
        return "L0"

    # L1 — drafting / planning (local artifacts).
    for kw in _L1_KEYWORDS:
        if kw in t:
            return "L1"

    # T63 — if an effect was supplied and is not on the allow-list, the
    # action is at least L1 (unknown effects are never L0).
    if effect is not None and not _is_allowed_l0_effect(effect):
        return "L1"

    # Default — observe only.
    return "L0"


def attach_risk(action: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *action* with ``risk_level`` set via :func:`classify`.

    If ``risk_level`` is already present it is recomputed from the title
    (and ``kind``/``effect_type`` when available) so the field always
    reflects the canonical classification.

    **T63:**  When the action carries a ``kind`` or ``effect_type`` field,
    it is passed as the *effect* argument to :func:`classify` so that
    unknown effects are never classified as ``L0``.
    """
    result = dict(action)
    effect = result.get("effect_type") or result.get("kind")
    result["risk_level"] = classify(result.get("title", ""), effect)
    return result
