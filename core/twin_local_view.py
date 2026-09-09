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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_actions import list_actions
from core.twin_home import _work_products_dir, render_home

# Expose the resolved env-var name as a module-level attribute on ``os``
# so callers and tooling can introspect whether the data directory was
# configured (T86).
os.AEGIS_DATA_DIR = os.getenv("AEGIS_DATA_DIR", "")

# T123 — optional risk-TTL for the operator-visible warning flag.  After
# this many hours a proposed row's ``risk_warn`` flag may drop, but the
# row **never** auto-approves or auto-executes — status stays ``proposed``.
RISK_TTL_HOURS: int = int(os.getenv("AEGIS_RISK_TTL_HOURS", "72"))


def _risk_label(risk_level: str | None) -> str:
    """Return a stable typed token for *risk_level*.

    Only ``L2`` and ``L3`` produce a non-empty token (``RISK_L2``,
    ``RISK_L3``); ``L0`` and ``L1`` produce an empty string so the
    operator card shows no risk phrase for low-risk rows.
    """
    if risk_level in ("L2", "L3"):
        return f"RISK_{risk_level}"
    return ""


def _risk_warn(action: dict[str, Any]) -> bool:
    """Return True when the row's risk warning flag is still active.

    T123 — the warning may expire after ``RISK_TTL_HOURS`` (measured from
    ``created_at``), but expiry only drops the flag; it never approves
    or executes the row.  Status stays ``proposed``.
    """
    from core.twin_risk import classify

    risk = action.get("risk_level") or ""
    if not risk:
        risk = classify(action.get("title", ""), action.get("kind"))
    if risk not in ("L2", "L3"):
        return False
    created = action.get("created_at") or ""
    if not created:
        return True  # no timestamp — keep the flag
    try:
        dt = datetime.fromisoformat(created)
    except (ValueError, TypeError):
        return True  # unparseable — keep the flag
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    return age <= RISK_TTL_HOURS


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

    The returned dict has four keys:

    * ``pending`` — actions whose status is ``"proposed"``, sorted by
      deterministic priority (T117).
    * ``approved_waiting`` — actions whose status is ``"approved"``
      (approved but not yet executed).
    * ``latest`` — proposed actions whose ``batch_id`` equals the
      newest propose batch for *tenant_id* (T120).  When no batch_id
      exists on any row, ``latest`` is empty.
    * ``archive`` — proposed actions whose ``batch_id`` differs from
      the newest batch, plus proposed rows whose ``batch_id`` is
      ``None`` (older rows without a batch_id are treated as archive).

    Actions with status ``"executed"`` or ``"rejected"`` are excluded
    from all four lists.  No network libraries are used — the data is
    read from the local SQLite database only.
    """
    from core.priority import sort_actions

    actions = list_actions(tenant_id)
    pending: list[dict[str, Any]] = []
    approved_waiting: list[dict[str, Any]] = []
    for a in actions:
        status = a.get("status", "")
        if status == "proposed":
            pending.append(a)
        elif status == "approved":
            approved_waiting.append(a)
    pending = sort_actions(pending)

    # T123 — enrich each proposed row with ``digest_label`` (a stable
    # typed risk token such as ``RISK_L2`` / ``RISK_L3`` that appears in
    # the operator-visible digest text on the card) and ``risk_warn``
    # (the TTL-bound warning flag that may expire but never auto-acts).
    from core.twin_risk import attach_risk

    for a in pending:
        a.setdefault("risk_level", attach_risk(a).get("risk_level", ""))
        a["digest_label"] = _risk_label(a.get("risk_level"))
        a["risk_warn"] = _risk_warn(a)

    # T120 — split proposed rows into latest vs archive by batch_id.
    newest_batch = _newest_batch_id(pending)
    latest: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for a in pending:
        bid = a.get("batch_id")
        if bid is not None and bid == newest_batch:
            latest.append(a)
        else:
            archive.append(a)

    # T137 — enrich each approved row with the operator-visible fields:
    # agent (from kind prefix), title/task excerpt, digest prefix, and
    # approved timestamp.  Rejected actions are excluded.
    for a in approved_waiting:
        kind_str = a.get("kind", "")
        a["agent"] = kind_str.split(":")[0] if ":" in kind_str else kind_str
        a["digest_prefix"] = (a.get("payload_sha256", "") or "")[:12]
        a["approved_at"] = a.get("approved_at", "")

    return {
        "pending": pending,
        "approved_waiting": approved_waiting,
        "latest": latest,
        "archive": archive,
    }


def _newest_batch_id(pending: list[dict[str, Any]]) -> str | None:
    """Return the batch_id of the newest propose batch among *pending*.

    The newest batch is the batch_id of the most recently created
    proposed row that has a non-null batch_id.  Returns ``None`` when no
    pending row has a batch_id.
    """
    newest: str | None = None
    newest_created: str = ""
    for a in pending:
        bid = a.get("batch_id")
        if not bid:
            continue
        created = a.get("created_at", "")
        if created >= newest_created:
            newest = bid
            newest_created = created
    return newest
