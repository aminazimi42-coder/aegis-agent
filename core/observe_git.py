"""T209 — Local desk-slip export and git observe-only.

Two read-only local controls for the operator page:

1. **Desk slip** — writes one markdown file under
   ``AEGIS_DATA_DIR/export/desk_slip_YYYYMMDDThhmmssZ.md`` for the
   current tenant only.  The file may include the current tenant
   prefix, the last task string if present, and the last approve /
   reject ids already on disk.  No PII from outside the data dir.
   No cloud.  A caller-specified ``out_path`` outside the data dir is
   a typed deny (T190 ``cage_path``).

2. **Git observe** — observes ``git status`` plus at most the last
   five commit subjects under ``AEGIS_DATA_DIR/work`` only.  A
   missing work dir is a typed miss, not a crash.  No patch body, no
   remotes, no credentials.  The handler never calls ``git add``,
   ``git commit``, ``git push``, ``git reset --hard``, or
   ``git checkout``.  A request that would write the work tree is a
   typed deny ``GIT_OBSERVE_WRITE_DENIED``.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from core.twin_local_view import cage_path, data_root


class GitObserveWriteDeniedError(ValueError):
    """Typed rejection when a git-observe request would write the work tree.

    The ``code`` attribute is the stable typed string returned to both
    HTTP and CLI callers.
    """

    code: str = "GIT_OBSERVE_WRITE_DENIED"

    def __init__(self, reason: str = "git observe write denied") -> None:
        super().__init__(reason)
        self.reason = reason


class GitObserveMissingError(ValueError):
    """Typed miss when the work dir does not exist under the data root."""

    code: str = "git_observe_work_dir_missing"

    def __init__(self, reason: str = "git observe work dir missing") -> None:
        super().__init__(reason)
        self.reason = reason


def _last_task_string(tenant_id: str) -> str:
    """Return the last task string from the session receipt, or ``""``."""
    try:
        from core.session_receipt import read_session_receipt

        receipt = read_session_receipt(tenant_id)
        if receipt:
            task = receipt.get("last_task", "")
            if isinstance(task, str):
                return task
    except Exception:
        pass
    return ""


def _last_approve_reject_ids(tenant_id: str) -> dict[str, str]:
    """Return the last approve and reject action ids already on disk."""
    ids: dict[str, str] = {"last_approve_id": "", "last_reject_id": ""}
    try:
        from core.twin_actions import list_actions

        last_approve = ""
        last_reject = ""
        for row in list_actions(tenant_id):
            status = row.get("status", "")
            aid = row.get("action_id", "")
            if not aid:
                continue
            if status == "executed" and not last_approve:
                last_approve = aid
            elif status == "rejected" and not last_reject:
                last_reject = aid
        ids["last_approve_id"] = last_approve
        ids["last_reject_id"] = last_reject
    except Exception:
        pass
    return ids


def write_desk_slip(
    tenant_id: str,
    *,
    out_path: str | None = None,
) -> dict[str, Any]:
    """Write one desk-slip markdown file under ``AEGIS_DATA_DIR/export/``.

    The file is named ``desk_slip_YYYYMMDDThhmmssZ.md`` and is caged to
    the data root (T190).  The body may include the current tenant
    prefix, the last task string if present, and the last approve /
    reject ids already on disk.  No PII from outside the data dir.
    No cloud, no execute, no send.

    When *out_path* is provided it must resolve inside the data root;
    a path outside the data root is a typed deny
    (:class:`~core.twin_local_view.PathDeniedError`) with no write.

    Returns ``{tenant_id, path, sha256}``.
    """
    root = data_root()
    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if out_path:
        caged = cage_path(out_path)
        final_path = caged
    else:
        final_path = cage_path(export_dir / f"desk_slip_{stamp}.md")

    last_task = _last_task_string(tenant_id)
    ids = _last_approve_reject_ids(tenant_id)

    lines: list[str] = [
        f"# Desk slip — {tenant_id}",
        "",
        f"tenant_id: {tenant_id}",
        f"written_at: {stamp}",
    ]
    if last_task:
        lines.append(f"last_task: {last_task}")
    if ids["last_approve_id"]:
        lines.append(f"last_approve_id: {ids['last_approve_id']}")
    if ids["last_reject_id"]:
        lines.append(f"last_reject_id: {ids['last_reject_id']}")
    lines.append("")
    body = "\n".join(lines)

    import hashlib

    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    final_path.write_text(body + f"\nsha256: {sha}\n", encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": str(final_path),
        "sha256": sha,
    }


def observe_git(tenant_id: str) -> dict[str, Any]:
    """Observe ``git status`` and last five subjects under ``AEGIS_DATA_DIR/work``.

    The target directory is ``AEGIS_DATA_DIR/work`` only.  A missing
    work dir is a typed miss (:class:`GitObserveMissingError`), not a
    crash.  The result is the local status string plus at most the
    last five commit subjects.  No patch body, no remotes, no
    credentials.

    The handler never calls ``git add``, ``git commit``, ``git
    push``, ``git reset --hard``, or ``git checkout``.  A request
    that would write the work tree is a typed deny
    (:class:`GitObserveWriteDeniedError`).

    Returns ``{tenant_id, status, subjects, count}``.
    """
    root = data_root()
    work_dir = root / "work"
    if not work_dir.is_dir():
        raise GitObserveMissingError("git observe work dir missing")
    if not (work_dir / ".git").exists():
        raise GitObserveMissingError("git observe work dir is not a repo")

    env = {**_safe_env(), "GIT_TERMINAL_PROMPT": "0"}

    # git status — porcelain, no color, local only.
    status_proc = subprocess.run(
        ["git", "-C", str(work_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
        env=env,
    )
    status_text = status_proc.stdout.strip() if status_proc.returncode == 0 else ""

    # git log — last five subjects only, no patch body, no remotes.
    log_proc = subprocess.run(
        [
            "git",
            "-C",
            str(work_dir),
            "log",
            "-n5",
            "--format=%s",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    subjects: list[str] = []
    if log_proc.returncode == 0:
        for line in log_proc.stdout.splitlines():
            line = line.strip()
            if line:
                subjects.append(line)

    return {
        "tenant_id": tenant_id,
        "status": status_text or "clean",
        "subjects": subjects,
        "count": len(subjects),
    }


def _safe_env() -> dict[str, str]:
    """Return a sanitized env for git subprocesses — no credentials."""
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "LANG", "LC_ALL"):
        val = __import__("os").environ.get(key)
        if val:
            env[key] = val
    return env


def denied_git_commands() -> frozenset[str]:
    """Return the frozenset of git subcommands that are always a typed deny."""
    return frozenset({"add", "commit", "push", "reset --hard", "checkout"})
