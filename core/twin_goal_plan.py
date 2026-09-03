"""Goal text to ordered proposed-action plan (T42).

``plan_goal(tenant_id, text)`` turns one paragraph of intent into an ordered
list of proposed actions.  Each step is persisted via the existing
``propose_actions`` machinery (or equivalent) so its status starts as
``proposed`` — the human still approves; nothing is executed, emailed, or
sent over the network.

A markdown file ``goal_plan.md`` is written (overwritten on each call) under
``{AEGIS_DATA_DIR}/work_products/{tenant_id}/`` with the ordered step titles.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.twin_interview import get_latest_profile
from core.twin_risk import classify

# ---------------------------------------------------------------------------#
# Helpers
# ---------------------------------------------------------------------------#

_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s*(.+)$")


def _split_steps(text: str) -> list[str]:
    """Split *text* into 2–8 ordered step titles.

    If the text contains numbered lines (``1.``, ``2.``, …) those are used
    as the steps.  Otherwise the text is split by sentence boundaries.
    The result is clamped to [2, 8].
    """
    # Try numbered lines first.
    numbered: list[str] = []
    for line in text.splitlines():
        m = _NUMBERED_RE.match(line)
        if m:
            numbered.append(m.group(1).strip())

    if numbered:
        steps = numbered
    else:
        # Split on sentence-ending punctuation followed by whitespace.
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
        steps = sentences

    # Clamp to [2, 8].
    if len(steps) < 2:
        # Pad by repeating the single step with an ordinal qualifier.
        if steps:
            steps = [steps[0], f"Follow up on: {steps[0]}"]
        else:
            steps = ["Review the goal", "Plan next steps"]
    if len(steps) > 8:
        steps = steps[:8]
    return steps


def _work_products_dir(tenant_id: str) -> Path:
    """Return the work-products directory for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def plan_goal(tenant_id: str, text: str) -> dict[str, Any]:
    """Turn *text* into an ordered list of proposed actions for *tenant_id*.

    Requires a consented profile (otherwise ``ValueError("no consented
    profile")`` is raised).

    Splits the text into 2–8 steps (numbered lines if present, else
    sentences).  Each step is persisted through ``propose_actions`` so the
    status starts as ``proposed``.  A markdown file ``goal_plan.md`` is
    written (overwriting any prior version) under
    ``{AEGIS_DATA_DIR}/work_products/{tenant_id}/``.

    Does **not** approve, execute, email, or open sockets.

    Returns a dict with ``tenant_id``, ``path`` (the markdown file), and
    ``action_ids`` (the list of created action IDs).
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    steps = _split_steps(text)

    # Persist one proposed action per step so each is individually trackable.
    # We insert directly with status "proposed" — the human still approves.
    from core.twin_actions import _ensure_schema as _ensure_actions_schema

    _ensure_actions_schema()
    from core.persistence import get_connection

    now = datetime.now(timezone.utc).isoformat()
    action_ids: list[str] = []
    with get_connection() as conn:
        for title in steps:
            aid = f"act-{uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (aid, tenant_id, "goal_plan", title, "proposed", now),
            )
            action_ids.append(aid)

    # Write the goal_plan.md file.
    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "goal_plan.md"

    # Attach risk_level to each step for the markdown and the return dict.
    risk_levels: list[str] = []
    lines: list[str] = [f"# Goal Plan — {tenant_id}", ""]
    for i, title in enumerate(steps, start=1):
        rl = classify(title)
        risk_levels.append(rl)
        lines.append(f"{i}. [{rl}] {title}")
    lines.append("")

    plan_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": plan_path.as_posix(),
        "action_ids": action_ids,
        "risk_levels": risk_levels,
    }