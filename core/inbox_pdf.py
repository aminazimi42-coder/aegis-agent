"""Caged inbox image to local signed PDF (T218).

``build_signed_inbox_pdf(tenant_id, image_relpath)`` reads a single
image that already sits under ``AEGIS_DATA_DIR/inbox/<name>`` and writes
a one-page signed PDF under ``AEGIS_DATA_DIR/export/`` plus a detached
``.sig`` sibling.

No network fetch of images.  No renderer that shells out to ``curl``.
The PDF body is local bytes only — a minimal one-page PDF with text
lines showing the caged source path, the sha256 of the image bytes, and
the word ``Intact`` after the write completes.

A path outside ``AEGIS_DATA_DIR`` is a typed deny
(:class:`PathDeniedError`).  A missing inbox file is a typed
``ValueError("INBOX_MISSING")``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import PathDeniedError, cage_path, data_root

# ---------------------------------------------------------------------------#
# Helpers
# ---------------------------------------------------------------------------#


class InboxMissingError(ValueError):
    """Typed rejection when the inbox image file does not exist."""

    code: str = "INBOX_MISSING"


def _inbox_dir() -> Path:
    """Return the inbox directory under the data root."""
    return data_root() / "inbox"


def _export_dir() -> Path:
    """Return the export directory under the data root."""
    return data_root() / "export"


def _escape_pdf_text(text: str) -> str:
    """Escape parentheses and backslashes for a PDF text-showing operator."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_one_page_pdf(lines: list[str]) -> bytes:
    """Return bytes for a minimal one-page PDF showing *lines* of text.

    The PDF is a single A4-portrait page with each line rendered at
    ``y = 750 - i * 20`` using a built-in Helvetica font.  No external
    assets, no embedded images, no compression — just the raw content
    stream and cross-reference table.
    """
    # Build the content stream: set font, then show each line.
    content_ops: list[str] = ["BT", "/F1 12 Tf", "1 0 0 1 50 750 Tm"]
    for i, line in enumerate(lines):
        y = 750 - i * 20
        escaped = _escape_pdf_text(line)
        content_ops.append(f"1 0 0 1 50 {y} Tm")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    content_stream = "\n".join(content_ops) + "\n"

    # Build the PDF objects.
    # Object 1: Catalog
    # Object 2: Pages
    # Object 3: Page
    # Object 4: Font
    # Object 5: Contents
    objects: list[bytes] = []
    offsets: list[int] = []

    header = b"%PDF-1.4\n"

    def add_obj(body: str) -> int:
        """Append an object body and return its number (1-indexed)."""
        obj_num = len(objects) + 1
        obj_bytes = f"{obj_num} 0 obj\n{body}\nendobj\n".encode("latin-1")
        objects.append(obj_bytes)
        return obj_num

    # Object numbers are fixed: 1=Catalog, 2=Pages, 3=Page,
    # 4=Font, 5=Contents.
    pages_num = 2
    page_num = 3
    font_num = 4
    contents_num = 5

    catalog_body = f"<< /Type /Catalog /Pages {pages_num} 0 R >>"
    pages_body = (
        f"<< /Type /Pages /Kids [{page_num} 0 R] /Count 1 >>"
    )
    page_body = (
        f"<< /Type /Page /Parent {pages_num} 0 R "
        f"/MediaBox [0 0 595 842] "
        f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
        f"/Contents {contents_num} 0 R >>"
    )
    font_body = (
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )
    contents_body = (
        f"<< /Length {len(content_stream.encode('latin-1'))} >>\n"
        f"stream\n{content_stream}endstream"
    )

    obj_bodies = [
        catalog_body,
        pages_body,
        page_body,
        font_body,
        contents_body,
    ]

    # Now assemble the full PDF.
    pdf_bytes = header
    for i, body in enumerate(obj_bodies, start=1):
        offsets.append(len(pdf_bytes))
        pdf_bytes += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")

    # Cross-reference table.
    xref_offset = len(pdf_bytes)
    xref_lines = ["xref", f"0 {len(obj_bodies) + 1}", "0000000000 65535 f "]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n ")
    xref_table = "\n".join(xref_lines) + "\n"
    pdf_bytes += xref_table.encode("latin-1")

    # Trailer.
    trailer = (
        f"trailer\n<< /Size {len(obj_bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf_bytes += trailer.encode("latin-1")

    return pdf_bytes


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def build_signed_inbox_pdf(tenant_id: str, image_relpath: str) -> dict[str, Any]:
    """Build a one-page signed PDF from a caged inbox image.

    *tenant_id* identifies the caller.  *image_relpath* is a path
    relative to ``AEGIS_DATA_DIR/inbox/`` (or an absolute path inside
    that directory).  The image must already sit under
    ``AEGIS_DATA_DIR/inbox/`` — no network fetch.

    Writes ``export/inbox_<utc>.pdf`` and ``inbox_<utc>.pdf.sig``
    under ``AEGIS_DATA_DIR/export/``.

    Raises :class:`PathDeniedError` when the resolved image path
    escapes ``AEGIS_DATA_DIR``.  Raises :class:`InboxMissingError`
    when the file does not exist on disk.

    Returns ``{tenant_id, path, sha256, sig_path, verify}``.
    """
    inbox = _inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)

    # Resolve the image path relative to the inbox dir, then cage it
    # against the data root.  A path outside AEGIS_DATA_DIR is a typed
    # deny — never opened.
    if Path(image_relpath).is_absolute():
        image_path = cage_path(Path(image_relpath))
    else:
        image_path = cage_path(inbox / image_relpath)

    # The caged path must also live under the inbox dir.
    inbox_resolved = inbox.resolve()
    image_resolved = image_path.resolve()
    try:
        image_resolved.relative_to(inbox_resolved)
    except ValueError:
        raise PathDeniedError("path outside AEGIS_DATA_DIR/inbox") from None

    if not image_path.is_file():
        raise InboxMissingError("INBOX_MISSING")

    # Read the image bytes (local only) and compute sha256.
    image_bytes = image_path.read_bytes()
    image_sha = hashlib.sha256(image_bytes).hexdigest()

    # Build the PDF page text: path + sha256 + Intact.
    export = _export_dir()
    export.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdf_name = f"inbox_{stamp}.pdf"
    pdf_path = cage_path(export / pdf_name)

    rel_path = str(image_path.relative_to(data_root()))
    page_lines: list[str] = [
        f"Inbox image export - {tenant_id}",
        "",
        f"Source path: {rel_path}",
        f"sha256: {image_sha}",
        "Intact",
        f"Exported at: {stamp}",
    ]
    pdf_bytes = _build_one_page_pdf(page_lines)
    pdf_path.write_bytes(pdf_bytes)

    # Detached .sig sibling (like the T178 brief export).  The .sig
    # stores the sha256 of the **PDF file bytes** so the verify step
    # recomputes sha256(pdf) and compares — the same pattern as the
    # text-based brief export, adapted for a binary PDF.
    if not pdf_path.is_file():
        raise ValueError("missing_file")
    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    sig_path = pdf_path.with_suffix(pdf_path.suffix + ".sig")
    sig_content = f"sha256: {pdf_sha}\nsigner: aegis-local\n"
    sig_path.write_text(sig_content, encoding="utf-8")

    # Verify after write — recompute sha256 of the PDF bytes and compare
    # against the value stored in the .sig sibling.  Reports Intact
    # when they match, Tampered when they do not, Missing when either
    # file is absent.
    verify_status: str
    if not pdf_path.is_file():
        verify_status = "export_verify_failed: missing_file"
    elif not sig_path.is_file():
        verify_status = "export_verify_failed: missing_sig"
    else:
        recomputed = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        stored_sha: str | None = None
        for sline in sig_path.read_text("utf-8").splitlines():
            if sline.startswith("sha256:"):
                stored_sha = sline.split("sha256:", 1)[1].strip()
                break
        if stored_sha is not None and stored_sha == recomputed:
            verify_status = "Intact"
        else:
            verify_status = "Tampered"

    return {
        "tenant_id": tenant_id,
        "path": str(pdf_path),
        "sha256": image_sha,
        "sig_path": str(sig_path),
        "verify": verify_status,
    }
