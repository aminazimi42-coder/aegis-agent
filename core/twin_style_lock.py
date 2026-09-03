"""Lock a deterministic writing-style profile from local text samples.

``lock_style(tenant_id, samples_dir)`` reads ``*.txt`` and ``*.md`` files from
*samples_dir*, tokenizes them (lowercase ``[a-z0-9]+``, dropping tokens shorter
than four characters), computes the twelve most frequent words, and writes
``work_products/{tenant_id}/style_lock.md`` with Voice notes and the top words.

The file is overwritten on each call — no LLM, no network.

Requires a consented twin profile (raises ``ValueError("no consented
profile")`` otherwise).  Requires ``samples_dir`` to be an existing directory
(raises ``ValueError("samples dir not found")`` otherwise).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _style_lock_path(tenant_id: str) -> Path:
    """Return the path to ``style_lock.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "style_lock.md"


def _tokenize(text: str) -> list[str]:
    """Tokenize *text* into lowercase tokens of length >= 4."""
    return [w for w in _TOKEN_RE.findall(text.lower()) if len(w) >= 4]


def _read_samples(samples_dir: Path) -> list[str]:
    """Read all ``*.txt`` and ``*.md`` files in *samples_dir* (utf-8, ignore errors)."""
    contents: list[str] = []
    for pattern in ("*.txt", "*.md"):
        for path in sorted(samples_dir.glob(pattern)):
            if path.is_file():
                contents.append(path.read_text(encoding="utf-8", errors="ignore"))
    return contents


def _top_words(contents: list[str], count: int = 12) -> list[str]:
    """Return the *count* most frequent words across all *contents*."""
    counter: Counter[str] = Counter()
    for text in contents:
        counter.update(_tokenize(text))
    return [word for word, _ in counter.most_common(count)]


def _build_style_lock_md(tenant_id: str, sample_count: int, top_words: list[str]) -> str:
    """Render the ``style_lock.md`` markdown content."""
    lines: list[str] = [
        f"# Style Lock — {tenant_id}",
        "",
        "## Voice Notes",
        "",
        "- Preferred vocabulary skews toward the top words listed below.",
        "- Keep sentences short and concrete; favour active voice.",
        "- Avoid jargon unless the term appears in the top-words list.",
        "- Maintain a consistent register across all written output.",
        "",
        "## Top Words",
        "",
    ]
    if top_words:
        for i, word in enumerate(top_words, start=1):
            lines.append(f"{i}. {word}")
    else:
        lines.append("_No words found in samples._")
    lines.append("")
    return "\n".join(lines)


def lock_style(tenant_id: str, samples_dir: str) -> dict[str, Any]:
    """Lock a writing-style profile from local text samples.

    Reads ``*.txt`` and ``*.md`` files from *samples_dir*, tokenizes them
    (lowercase ``[a-z0-9]+``, dropping tokens shorter than four characters),
    computes the twelve most frequent words, and writes
    ``work_products/{tenant_id}/style_lock.md``.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *samples_dir* to be an existing
    directory (raises ``ValueError("samples dir not found")`` otherwise).

    Overwrites the output file on each call.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    sdir = Path(samples_dir)
    if not sdir.is_dir():
        raise ValueError("samples dir not found")

    contents = _read_samples(sdir)
    top_words = _top_words(contents, count=12)

    out_path = _style_lock_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = _build_style_lock_md(tenant_id, len(contents), top_words)
    out_path.write_text(md_content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
        "sample_count": len(contents),
        "top_words": top_words,
    }
