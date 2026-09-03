"""T34 — Local audio sidecar to a proposed twin action.

If the principal drops ``note.wav`` plus ``note.txt`` next to it, treat the
``.txt`` file as the transcript and reuse :func:`core.twin_transcript_task.
from_transcript` to produce one proposed twin action.

No audio decode — no cloud speech-to-text, no Whisper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile
from core.twin_transcript_task import from_transcript


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    import os

    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def from_audio(tenant_id: str, audio_path: str) -> dict[str, Any]:
    """Turn a local audio file plus its ``.txt`` sidecar into one proposed task.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *audio_path* to be an existing file
    (raises ``ValueError("audio not found")`` otherwise).  Requires a sibling
    ``.txt`` file with the same stem (raises ``ValueError("transcript sidecar
    not found")`` otherwise).

    Delegates to :func:`core.twin_transcript_task.from_transcript` for the
    actual title-derivation and action proposal, then writes
    ``work_products/{tenant_id}/audio_task.md`` (overwriting any previous file)
    pointing at the sidecar name.

    Returns ``{tenant_id, action_id, path, title, sidecar}``.
    """
    # 1. Consent gate.
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    # 2. Audio file gate.
    audio = Path(audio_path)
    if not audio.is_file():
        raise ValueError("audio not found")

    # 3. Sidecar gate.
    sidecar = audio.with_suffix(".txt")
    if not sidecar.is_file():
        raise ValueError("transcript sidecar not found")

    # 4. Delegate to the transcript-to-task flow.
    result = from_transcript(tenant_id, str(sidecar))
    action_id = result["action_id"]
    title = result["title"]

    # 5. Write the audio-task markdown pointing at the sidecar name.
    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "audio_task.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sidecar_name = sidecar.name
    lines = [
        f"# Audio Task — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        f"**Action ID:** {action_id}",
        f"**Title:** {title}",
        f"**Sidecar:** {sidecar_name}",
        "",
        "## Source",
        "",
        f"Audio: `{audio.name}`",
        f"Transcript sidecar: `{sidecar_name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "action_id": action_id,
        "path": str(md_path),
        "title": title,
        "sidecar": sidecar_name,
    }
