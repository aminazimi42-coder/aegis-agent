"""Local buyer one-pager export (T136).

Renders a short local ``.md`` file from the saved profile (name/role/
goals/timezone) plus honest shipped facts only — local twin, six
specialists propose-only, Echo default, approve/reject required, no card
in core.

The file is written only under ``AEGIS_DATA_DIR`` or
``~/.aegis/exports/`` — never into the git worktree, never as committed
PII beyond the already-saved profile display name.

When the profile is empty (no committed profile) a ``ValueError`` is
raised and no file is written.

No PDF library is a declared dependency of this project, so the output
is a plain UTF-8 ``.md`` file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile
from core.twin_local_view import data_root


def _exports_dir() -> Path:
    """Return the directory where one-pager files are written."""
    root = data_root()
    path = root / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename_component(name: str) -> str:
    """Return a filesystem-safe slug derived from *name*."""
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in (name or "").strip()
    )
    return safe or "operator"


def render_buyer_one_pager(tenant_id: str) -> dict[str, Any]:
    """Render a local buyer one-pager from the saved profile.

    Raises ``ValueError`` when no profile is committed for *tenant_id*.

    The file is written under ``{AEGIS_DATA_DIR}/exports/`` (or
    ``~/.aegis/exports/`` by default) — never inside the git worktree.

    Returns a dict with keys: ``tenant_id``, ``path``, ``filename``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    # Profile fields (from twin_interview mapping):
    #   repositories → display name
    #   role          → role
    #   decision_style → goals
    #   tools         → timezone
    display_name = profile.get("repositories", "") or "operator"
    role = profile.get("role", "") or ""
    goals = profile.get("decision_style", "") or ""
    tz = profile.get("tools", "") or ""

    slug = _safe_filename_component(display_name)
    filename = f"buyer_one_pager_{slug}.md"
    out_path = _exports_dir() / filename

    now = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# Aegis Agent — Buyer One-Pager",
        "",
        f"**Operator:** {display_name}",
        f"**Role:** {role}",
        f"**Goals:** {goals}",
        f"**Timezone:** {tz}",
        "",
        "## What is shipped (honest)",
        "",
        "- Local cognitive twin — runs on the operator's machine.",
        "- Six specialists (Alina, Kian, Bita, Aylin, Ahmad, Amin) "
        "propose only — nothing executes without human approval.",
        "- EchoProvider is the default LLM (offline echo); no paid "
        "cloud LLM is wired by default.",
        "- Approve/reject is required before any action executes.",
        "- No payment, card, or billing logic in the core repository.",
        "",
        f"_Generated: {now}_",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": str(out_path),
        "filename": filename,
    }
