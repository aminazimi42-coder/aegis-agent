"""Local home viewer — read home.md from disk without HTTP (T75).

``read_home(tenant_id)`` returns the text of
``work_products/{tenant_id}/home.md`` directly from the local filesystem.
If the file does not yet exist, :func:`render_home` is called first to
materialise it, then the freshly written file is read back.

No network libraries are used — the operator can read the home page from
``AEGIS_DATA_DIR`` without touching the network.
"""

from __future__ import annotations

from pathlib import Path

from core.twin_home import _work_products_dir, render_home


def read_home(tenant_id: str) -> str:
    """Return the markdown text of ``home.md`` for *tenant_id*.

    If ``home.md`` is not present on disk, :func:`render_home` is called
    first to write it, then the file is read back.  Returns the full
    markdown text.  Raises ``ValueError("no consented profile")`` when
    *tenant_id* has no committed profile (propagated from
    :func:`render_home`).
    """
    home_path: Path = _work_products_dir(tenant_id) / "home.md"
    if not home_path.is_file():
        render_home(tenant_id)
    return home_path.read_text(encoding="utf-8")
