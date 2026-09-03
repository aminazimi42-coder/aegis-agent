"""Local PR review notes from a unified diff file.

``review_diff(tenant_id, diff_path)`` reads a local unified diff, extracts
the file paths touched, and writes ``work_products/{tenant_id}/pr_review.md``
with the file list and a four-item deterministic checklist.

The checklist includes "Do not push to origin" as a safety guardrail.

Requires a consented twin profile (raises ``ValueError("no consented
profile")`` otherwise).  Requires ``diff_path`` to be an existing file
(raises ``ValueError("diff not found")`` otherwise).

Optionally ingests an event of ``source="git"`` and ``kind="review"`` —
if the kind is not accepted by the event ingester, the ingest is skipped
and the review file is still written.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event
from core.twin_interview import get_latest_profile


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _parse_diff_paths(diff_text: str) -> list[str]:
    """Extract file paths from unified diff text.

    Collects paths from lines starting with ``diff --git`` (takes the
    second token, which is ``a/path`` → ``path``) or ``+++ b/`` (takes
    the remainder after ``b/``).
    """
    paths: list[str] = []
    seen: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 3:
                # parts[1] is "a/path", parts[2] is "b/path"
                candidate = parts[2]
                if candidate.startswith("b/"):
                    candidate = candidate[2:]
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    paths.append(candidate)
        elif line.startswith("+++ b/"):
            candidate = line[len("+++ b/"):].strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                paths.append(candidate)
    return paths


def _build_pr_review_md(
    tenant_id: str,
    diff_path: str,
    files: list[str],
) -> str:
    """Render the ``pr_review.md`` markdown content."""
    lines: list[str] = [
        f"# PR Review — {tenant_id}",
        "",
        f"**Diff:** {diff_path}",
        "",
        "## Files Changed",
        "",
    ]
    if files:
        for f in files:
            lines.append(f"- {f}")
    else:
        lines.append("_No files detected in diff._")
    lines.append("")
    lines.append("## Checklist")
    lines.append("")
    lines.append("- [ ] Review every file listed above for correctness.")
    lines.append("- [ ] Confirm tests pass locally before merging.")
    lines.append("- [ ] Do not push to origin without explicit approval.")
    lines.append("- [ ] Verify no secrets or credentials are introduced.")
    lines.append("")
    return "\n".join(lines)


def review_diff(tenant_id: str, diff_path: str) -> dict[str, Any]:
    """Turn a local unified diff into review notes.

    Parses *diff_path* for changed file paths, writes
    ``work_products/{tenant_id}/pr_review.md`` with the file list and a
    four-item deterministic checklist (including "Do not push to
    origin"), and optionally ingests a ``git``/``review`` event.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *diff_path* to be an existing file
    (raises ``ValueError("diff not found")`` otherwise).

    Overwrites the output file on each call.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    dpath = Path(diff_path)
    if not dpath.is_file():
        raise ValueError("diff not found")

    diff_text = dpath.read_text(encoding="utf-8", errors="ignore")
    files = _parse_diff_paths(diff_text)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pr_review.md"
    out_path.write_text(
        _build_pr_review_md(tenant_id, diff_path, files),
        encoding="utf-8",
    )

    # Best-effort event ingest — skip if the kind is rejected.
    try:
        ingest_event(
            tenant_id=tenant_id,
            source="git",
            kind="review",
            payload={"files": files},
        )
    except ValueError:
        pass

    return {
        "tenant_id": tenant_id,
        "path": diff_path,
        "files": files,
    }
