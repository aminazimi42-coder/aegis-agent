"""Local expense notes from receipt text files.

``ingest_receipts(tenant_id, receipts_dir)`` reads each ``*.txt`` file in
*receipts_dir*, treats the first line as the vendor and the remaining
lines as the body, extracts a dollar amount if present, and writes
``work_products/{tenant_id}/expenses.md`` with a per-receipt summary.

The summary includes the vendor, the parsed amount (or ``unparsed``),
and the safety line ``Do not pay without written approval.``

Requires a consented twin profile (raises ``ValueError("no consented
profile")`` otherwise).  Requires *receipts_dir* to be an existing
directory (raises ``ValueError("receipts dir not found")`` otherwise).

Optionally ingests an event of ``source="finance"`` and ``kind="receipt"``
— if the source/kind is not accepted, the ingest is skipped and the
expenses file is still written.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event
from core.twin_interview import get_latest_profile

_AMOUNT_RE = re.compile(r"\$?\s*(\d+(?:\.\d{2})?)")


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _parse_amount(text: str) -> str:
    """Return the first dollar amount found in *text*, or ``"unparsed"``."""
    match = _AMOUNT_RE.search(text)
    if match:
        return match.group(1)
    return "unparsed"


def _read_receipts(receipts_dir: Path) -> list[dict[str, Any]]:
    """Read all ``*.txt`` files in *receipts_dir* and return receipt dicts."""
    receipts: list[dict[str, Any]] = []
    for path in sorted(receipts_dir.glob("*.txt")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        vendor = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        amount = _parse_amount(text)
        receipts.append(
            {
                "vendor": vendor,
                "amount": amount,
                "body": body,
            }
        )
    return receipts


def _build_expenses_md(
    tenant_id: str,
    receipts_dir: str,
    receipts: list[dict[str, Any]],
) -> str:
    """Render the ``expenses.md`` markdown content."""
    lines: list[str] = [
        f"# Expenses — {tenant_id}",
        "",
        f"**Receipts dir:** {receipts_dir}",
        "",
        f"**Receipt count:** {len(receipts)}",
        "",
        "## Receipts",
        "",
    ]
    if receipts:
        for r in receipts:
            lines.append(f"### {r['vendor']}")
            lines.append("")
            lines.append(f"- **Amount:** {r['amount']}")
            lines.append("")
    else:
        lines.append("_No receipts found._")
        lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append("Do not pay without written approval.")
    lines.append("")
    return "\n".join(lines)


def ingest_receipts(tenant_id: str, receipts_dir: str) -> dict[str, Any]:
    """Turn a folder of receipt ``.txt`` files into an expense note.

    Reads each ``*.txt`` file in *receipts_dir*, treats the first line as
    the vendor, parses a dollar amount from the text, and writes
    ``work_products/{tenant_id}/expenses.md`` with a per-receipt summary
    including the safety line ``Do not pay without written approval.``.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *receipts_dir* to be an existing
    directory (raises ``ValueError("receipts dir not found")`` otherwise).

    Overwrites the output file on each call.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    rdir = Path(receipts_dir)
    if not rdir.is_dir():
        raise ValueError("receipts dir not found")

    receipts = _read_receipts(rdir)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "expenses.md"
    out_path.write_text(
        _build_expenses_md(tenant_id, receipts_dir, receipts),
        encoding="utf-8",
    )

    # Best-effort event ingest — skip if the source/kind is rejected.
    try:
        ingest_event(
            tenant_id=tenant_id,
            source="finance",
            kind="receipt",
            payload={"count": len(receipts)},
        )
    except ValueError:
        pass

    return {
        "tenant_id": tenant_id,
        "path": str(out_path),
        "count": len(receipts),
    }
