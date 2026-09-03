"""Principal one-pager / resume pack for the cognitive twin.

``render_resume(tenant_id)`` produces a single markdown page — a compact
resume that a principal can hand to a stakeholder or paste into a profile.

The page is assembled from:

- **Name / role** — pulled from the consented twin profile fields that
  exist (missing fields are silently skipped).
- **Work products** — the filenames of every file currently sitting under
  ``work_products/{tenant_id}/``.
- **Decisions count** — the number of recorded yes/no decisions, if the
  ``twin_decisions`` module is importable and ``list_decisions`` works.

The file is written to
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/resume.md``
and overwritten on each call.

No live LLM, no network calls — pure computation over local SQLite tables
and the existing work-product directory.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _collect_work_product_filenames(tenant_id: str) -> list[str]:
    """Return the sorted filenames of files already under work_products/{tenant_id}/."""
    wp_dir = _work_products_dir(tenant_id)
    if not wp_dir.is_dir():
        return []
    return sorted(p.name for p in wp_dir.iterdir() if p.is_file())


def _decisions_count(tenant_id: str) -> int | None:
    """Return the number of recorded decisions, or ``None`` if unavailable."""
    try:
        from core.twin_decisions import list_decisions
    except ImportError:  # pragma: no cover — decisions module should exist
        return None
    try:
        return len(list_decisions(tenant_id))
    except Exception:  # pragma: no cover — never let decisions break the resume
        return None


def _build_resume(
    tenant_id: str,
    role: str,
    work_products: list[str],
    decisions_count: int | None,
    name: str = "",
) -> str:
    """Render the ``resume.md`` content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Resume — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
    ]

    # --- Name / role section (only fields that exist) ---
    if name:
        lines.append(f"**Name:** {name}")
        lines.append("")
    if role:
        lines.append(f"**Role:** {role}")
        lines.append("")

    # --- Work products section ---
    lines.append("## Work Products")
    lines.append("")
    if work_products:
        for fname in work_products:
            lines.append(f"- {fname}")
    else:
        lines.append("_No work products generated yet._")
    lines.append("")

    # --- Decisions section ---
    if decisions_count is not None:
        lines.append("## Decisions")
        lines.append("")
        lines.append(f"**Total recorded decisions:** {decisions_count}")
        lines.append("")

    lines.append("Do not act on this resume without written principal approval.")
    lines.append("")
    return "\n".join(lines)


def render_resume(tenant_id: str) -> dict[str, Any]:
    """Render a one-page principal resume for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Pulls Name/role from the profile fields that exist (skips missing),
    lists filenames under ``work_products/{tenant_id}/``, and includes a
    decisions count if ``list_decisions`` works.

    Writes ``work_products/{tenant_id}/resume.md`` (overwriting any previous
    file) and returns ``{tenant_id, path}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    role: str = profile.get("role") or ""
    name: str = profile.get("name") or ""
    work_products = _collect_work_product_filenames(tenant_id)
    decisions_count = _decisions_count(tenant_id)

    content = _build_resume(tenant_id, role, work_products, decisions_count, name)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "resume.md"
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
    }
