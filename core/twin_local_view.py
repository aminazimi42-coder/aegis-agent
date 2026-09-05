"""Local home viewer — read home.md and queue from disk/SQLite (T75, T76, T77).

``data_root()`` resolves ``AEGIS_DATA_DIR`` (or ``~/.aegis`` by default)
to an absolute :class:`~pathlib.Path`, creating the directory if needed,
and returns that path.  No network libraries are used.

``read_home(tenant_id)`` returns the text of
``work_products/{tenant_id}/home.md`` directly from the local filesystem.
If the file does not yet exist, :func:`render_home` is called first to
materialise it, then the freshly written file is read back.

``list_queue(tenant_id)`` returns a dict with keys ``pending`` and
``approved_waiting``, sourced solely from ``twin_actions`` in the local
SQLite database — no HTTP, no ``urllib``, no ``requests``, no sockets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_actions import list_actions
from core.twin_home import _work_products_dir, render_home

# Expose the resolved env-var name as a module-level attribute on ``os``
# so callers and tooling can introspect whether the data directory was
# configured (T86).
os.AEGIS_DATA_DIR = os.getenv("AEGIS_DATA_DIR", "")


def offline_mode() -> bool:
    """Return True when ``AEGIS_OFFLINE`` is enabled.

    Accepts ``1``, ``true``, or ``yes`` (case-insensitive). Any other
    value — including unset — returns ``False``.
    """
    return os.getenv("AEGIS_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def data_root() -> Path:
    """Return the absolute on-disk data root for the local view.

    When ``AEGIS_DATA_DIR`` is set and non-empty, that path is used
    (existing behavior).  Otherwise the default is ``~/.aegis`` (the
    user's home directory), **not** ``./data`` inside the repository
    tree.  The directory is created with ``parents=True, exist_ok=True``
    when it does not yet exist, and the absolute :class:`~pathlib.Path`
    is returned.

    No network libraries are used.
    """
    env_val = os.getenv("AEGIS_DATA_DIR", "")
    if env_val and env_val.strip():
        root = Path(env_val)
    else:
        root = Path.home() / ".aegis"
    if not root.is_absolute():  # pragma: no cover - env paths are usually absolute
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def provider_status() -> dict[str, Any]:
    """Return a dict describing which LLM path is active.

    Keys:

    * ``kind`` — ``"echo"`` when the active provider is
      :class:`~core.llm_provider.EchoProvider` (either because
      :func:`offline_mode` is True or because no HTTP provider is
      configured), or ``"http-fallback"`` when
      :func:`~core.llm_provider.get_provider` returns an
      :class:`~core.llm_provider.HttpProvider` and
      :func:`offline_mode` is False.
    * ``offline`` — the boolean value of :func:`offline_mode`.

    Does **not** call ``complete()`` or open any network connection;
    ``get_provider()`` only constructs a provider object.
    """
    from core.llm_provider import HttpProvider, get_provider

    is_offline = offline_mode()
    if is_offline:
        return {"kind": "echo", "offline": True}
    provider = get_provider()
    if isinstance(provider, HttpProvider):
        return {"kind": "http-fallback", "offline": False}
    return {"kind": "echo", "offline": False}


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


def list_queue(tenant_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return the local action queue for *tenant_id* from ``twin_actions``.

    The returned dict has two keys:

    * ``pending`` — actions whose status is ``"proposed"``.
    * ``approved_waiting`` — actions whose status is ``"approved"``
      (approved but not yet executed).

    Actions with status ``"executed"`` or ``"rejected"`` are excluded.
    No network libraries are used — the data is read from the local
    SQLite database only.
    """
    actions = list_actions(tenant_id)
    pending: list[dict[str, Any]] = []
    approved_waiting: list[dict[str, Any]] = []
    for a in actions:
        status = a.get("status", "")
        if status == "proposed":
            pending.append(a)
        elif status == "approved":
            approved_waiting.append(a)
    return {"pending": pending, "approved_waiting": approved_waiting}
