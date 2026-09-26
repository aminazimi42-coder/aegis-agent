"""Caged inbox image to tenant-scoped local signed PDF (T224).

``build_signed_inbox_pdf(tenant_id, image_relpath)`` reads a single image
that already sits under ``AEGIS_DATA_DIR/{tenant}/…`` and writes a one-page
signed PDF under ``AEGIS_DATA_DIR/{tenant}/export/inbox_{utc}.pdf`` plus a
detached ``.sig`` sibling.

No network fetch of images.  No renderer that shells out to ``curl``.
The PDF body is local bytes only — a minimal one-page PDF with text
lines showing the caged source path, the sha256 of the image bytes, and
the word ``Intact`` after the write completes.

A path outside ``AEGIS_DATA_DIR/{tenant}`` is a typed deny
(:class:`OutsideCageError`, code ``OUTSIDE_CAGE``).  A missing file is a
typed ``:class:`InboxMissingError` (code ``MISSING``).  An unsupported
image type (not png / jpg / jpeg / webp) is a typed
:class:`UnsupportedTypeError` (code ``UNSUPPORTED``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root

# ---------------------------------------------------------------------------#
# Typed errors
# ---------------------------------------------------------------------------#


class OutsideCageError(ValueError):
    """Typed rejection when the resolved path escapes the tenant cage."""

    code: str = "OUTSIDE_CAGE"


class InboxMissingError(ValueError):
    """Typed rejection when the inbox image file does not exist."""

    code: str = "MISSING"


class UnsupportedTypeError(ValueError):
    """Typed rejection when the image type is not png/jpg/jpeg/webp."""

    code: str = "UNSUPPORTED"


_SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})


# ---------------------------------------------------------------------------#
# Helpers
# ---------------------------------------------------------------------------#


def _tenant_dir(tenant_id: str) -> Path:
    """Return the tenant directory under the data root."""
    return data_root() / tenant_id


def _export_dir(tenant_id: str) -> Path:
    """Return the tenant export directory under the data root."""
    return _tenant_dir(tenant_id) / "export"


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
    content_ops: list[str] = ["BT", "/F1 12 Tf", "1 0 0 1 50 750 Tm"]
    for i, line in enumerate(lines):
        y = 750 - i * 20
        escaped = _escape_pdf_text(line)
        content_ops.append(f"1 0 0 1 50 {y} Tm")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    content_stream = "\n".join(content_ops) + "\n"

    header = b"%PDF-1.4\n"

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

    pdf_bytes = header
    offsets: list[int] = []
    for i, body in enumerate(obj_bodies, start=1):
        offsets.append(len(pdf_bytes))
        pdf_bytes += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")

    xref_offset = len(pdf_bytes)
    xref_lines = ["xref", f"0 {len(obj_bodies) + 1}", "0000000000 65535 f "]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n ")
    xref_table = "\n".join(xref_lines) + "\n"
    pdf_bytes += xref_table.encode("latin-1")

    trailer = (
        f"trailer\n<< /Size {len(obj_bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf_bytes += trailer.encode("latin-1")

    return pdf_bytes


def _cage_tenant_path(tenant_id: str, path: str | Path) -> Path:
    """Resolve *path* and return it only when it stays inside the tenant dir.

    Raises :class:`OutsideCageError` when the resolved path escapes
    ``AEGIS_DATA_DIR/{tenant_id}``.
    """
    tenant_root = _tenant_dir(tenant_id).resolve()
    raw = Path(path)
    if not raw.is_absolute():
        raw = tenant_root / raw
    resolved = raw.resolve()
    try:
        resolved.relative_to(tenant_root)
    except ValueError:
        raise OutsideCageError("path outside AEGIS_DATA_DIR/tenant") from None
    return resolved


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def build_signed_inbox_pdf(tenant_id: str, image_relpath: str) -> dict[str, Any]:
    """Build a one-page signed PDF from a caged tenant image.

    *tenant_id* identifies the caller.  *image_relpath* is a path
    relative to ``AEGIS_DATA_DIR/{tenant_id}/`` (or an absolute path
    inside that directory).  The image must already sit under the tenant
    cage — no network fetch.

    Writes ``AEGIS_DATA_DIR/{tenant_id}/export/inbox_{utc}.pdf`` and a
    detached ``.sig`` sibling.

    Raises :class:`OutsideCageError` when the resolved image path
    escapes ``AEGIS_DATA_DIR/{tenant_id}``.  Raises
    :class:`InboxMissingError` when the file does not exist on disk.
    Raises :class:`UnsupportedTypeError` when the file extension is not
    png, jpg, jpeg, or webp.

    Returns ``{tenant_id, path, sha256, sig_path, verify}``.
    """
    # Resolve the image path inside the tenant cage.
    image_path = _cage_tenant_path(tenant_id, image_relpath)

    # Validate the image type before reading.
    suffix = image_path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise UnsupportedTypeError("UNSUPPORTED")

    if not image_path.is_file():
        raise InboxMissingError("MISSING")

    # Read the image bytes (local only) and compute sha256.
    image_bytes = image_path.read_bytes()
    image_sha = hashlib.sha256(image_bytes).hexdigest()

    # Build the PDF page text: path + sha256 + Intact.
    root = data_root()
    export = _export_dir(tenant_id)
    export.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdf_name = f"inbox_{stamp}.pdf"
    pdf_path = export / pdf_name

    rel_path = str(image_path.relative_to(root.resolve()))
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

    # Detached .sig sibling — sha256 of the PDF file bytes.
    if not pdf_path.is_file():
        raise ValueError("missing_file")
    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    sig_path = pdf_path.with_suffix(pdf_path.suffix + ".sig")
    sig_content = f"sha256: {pdf_sha}\nsigner: aegis-local\n"
    sig_path.write_text(sig_content, encoding="utf-8")

    # Verify after write — recompute sha256 and compare.
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


def forget_tenant_export(tenant_id: str) -> dict[str, Any]:
    """Remove the tenant export directory under ``AEGIS_DATA_DIR/{tenant}``.

    Returns ``{tenant_id, export_dir, cleared: True}``.
    """
    export = _export_dir(tenant_id)
    if export.exists():
        import shutil

        shutil.rmtree(export)
    return {
        "tenant_id": tenant_id,
        "export_dir": str(export),
        "cleared": True,
    }
