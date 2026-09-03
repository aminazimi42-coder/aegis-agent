"""Unified twin API error payload helpers.

T35 — every twin route that catches a ValueError returns the same JSON
shape: ``{"detail": str(exc), "code": ..., "request_id": ...}`` with
HTTP 400.  The ``detail`` field is preserved verbatim so existing 400
tests continue to pass.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.responses import JSONResponse

# Exact-message → stable error-code mapping.
KNOWN: dict[str, str] = {
    "no consented profile": "TWIN_NO_PROFILE",
    "action not found": "TWIN_ACTION_MISSING",
    "not approved": "TWIN_NOT_APPROVED",
    "samples dir not found": "TWIN_SAMPLES_MISSING",
    "diff not found": "TWIN_DIFF_MISSING",
    "receipts dir not found": "TWIN_RECEIPTS_MISSING",
    "export not found": "TWIN_EXPORT_MISSING",
    "transcript not found": "TWIN_TRANSCRIPT_MISSING",
    "audio not found": "TWIN_AUDIO_MISSING",
    "transcript sidecar not found": "TWIN_SIDECAR_MISSING",
    "invalid duration": "TWIN_BAD_DURATION",
}

# Fallback code for any ValueError whose message is not in KNOWN.
TWIN_ERROR = "TWIN_ERROR"


def error_payload(exc: Exception, request_id: str | None = None) -> dict:
    """Build the canonical twin error body for *exc*.

    ``detail`` is always ``str(exc)`` unchanged.  ``code`` is looked up in
    :data:`KNOWN` and falls back to :data:`TWIN_ERROR`.  ``request_id``
    is the given value or a freshly generated ``uuid4`` hex digest.
    """
    detail = str(exc)
    code = KNOWN.get(detail, TWIN_ERROR)
    return {
        "detail": detail,
        "code": code,
        "request_id": request_id or uuid4().hex,
    }


def twin_value_error_response(exc: Exception, request_id: str | None = None) -> JSONResponse:
    """Return a 400 ``JSONResponse`` with the canonical twin error body."""
    return JSONResponse(
        status_code=400,
        content=error_payload(exc, request_id),
    )
