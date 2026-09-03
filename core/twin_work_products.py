"""Local work-product rendering for the cognitive twin.

``render(tenant_id)`` produces real, openable local files a CTO can read:
a weekly plan (``weekly_plan.md``) and repo review notes (``review_notes.md``).
The content is derived deterministically from the twin's behavioral snapshot
and profile layers — no live LLM, no network calls.

Files are written under ``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/``
and overwritten on each render.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_behavior import get_behavior, rebuild
from core.twin_interview import get_latest_profile


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _weekly_plan(
    tenant_id: str,
    role: str,
    repos: list[str],
    event_count: int,
) -> str:
    """Render the weekly plan markdown content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Weekly Plan — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
    ]
    if role:
        lines.append(f"**Role:** {role}")
        lines.append("")
    lines.append(f"**Events this week:** {event_count}")
    lines.append("")
    lines.append("## Repositories")
    lines.append("")
    if repos:
        for repo in repos:
            lines.append(f"- {repo}")
    else:
        lines.append("_No repositories tracked yet._")
    lines.append("")
    lines.append("## Next Actions")
    lines.append("")
    lines.append("- Review the latest commits across tracked repositories.")
    lines.append("- Update the weekly status summary for stakeholders.")
    lines.append("- Triage open items and prioritise the top three for next week.")
    lines.append("")
    return "\n".join(lines)


def _review_notes(tenant_id: str, repos: list[str]) -> str:
    """Render the review-notes markdown content — one section per repo."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Review Notes — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
    ]
    if not repos:
        lines.append("_No repositories to review._")
        lines.append("")
        return "\n".join(lines)

    for repo in repos:
        lines.append(f"## {repo}")
        lines.append("")
        lines.append(
            f"- **Summary:** {repo} was active this week; review recent commits "
            "for correctness and completeness."
        )
        lines.append("- **Risk:** No critical issues flagged — continue routine review.")
        lines.append("- **Follow-up:** Confirm CI is green and merge queued PRs.")
        lines.append("")

    return "\n".join(lines)


def render(tenant_id: str) -> dict[str, Any]:
    """Render local work-product files for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    If no behavioral snapshot exists yet, ``rebuild()`` is called first
    (safe — it is idempotent when already present).

    Writes ``weekly_plan.md`` and ``review_notes.md`` under
    ``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/`` and returns a
    dict with ``tenant_id``, ``dir``, and ``files`` (absolute paths).
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    # Ensure a behavioral snapshot exists (idempotent).
    if get_behavior(tenant_id) is None:
        rebuild(tenant_id)

    behavior = get_behavior(tenant_id)
    snapshot: dict[str, Any] = behavior["snapshot"] if behavior else {}

    # Derive repos from behavior snapshot or fall back to profile layers.
    repos: list[str] = list(snapshot.get("repos") or [])
    if not repos:
        repos_raw = (profile.get("repositories") or "").strip()
        if repos_raw:
            repos = [r.strip() for r in repos_raw.split(",") if r.strip()]

    event_count: int = int(snapshot.get("event_count", 0))
    role: str = profile.get("role") or ""

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    plan_path = out_dir / "weekly_plan.md"
    review_path = out_dir / "review_notes.md"

    plan_content = _weekly_plan(tenant_id, role, repos, event_count)
    review_content = _review_notes(tenant_id, repos)

    plan_path.write_text(plan_content, encoding="utf-8")
    review_path.write_text(review_content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "dir": out_dir.as_posix(),
        "files": [
            plan_path.as_posix(),
            review_path.as_posix(),
        ],
    }
