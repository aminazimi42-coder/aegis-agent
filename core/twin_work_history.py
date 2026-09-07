"""Local work-product history: evidence pack, resume diff, memo diff (T101).

Provides three zero-network local commands:

* ``evidence_pack(tenant_id)`` — writes one markdown pack that records the
  local git-observe range (latest commit SHA + count) when a repo path is
  configured, else records "no git repo".

* ``resume_diff(tenant_id)`` — returns a unified diff of the last two
  hashed copies of ``resume.md`` renders.  If fewer than two hashed copies
  exist, returns an empty string (exit 0).

* ``memo_diff(tenant_id)`` — same for the last two ``board_memo.md`` hashed
  copies.

Hashed copies are written by ``render_resume`` and ``render_memo`` under
``work_products/{tenant_id}/_hashes/{resume|board_memo}/{sha256}.md`` so that
identical renders collapse to one file and the diff only fires when content
actually changed.

No live network — pure local filesystem and local ``git log`` only.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile
from core.twin_local_view import data_root

# ---------------------------------------------------------------------------#
# Paths
# ---------------------------------------------------------------------------#


def _work_products_dir(tenant_id: str) -> Path:
    """Return the work-products directory for *tenant_id*."""
    return data_root() / "work_products" / tenant_id


def _hashes_dir(tenant_id: str, kind: str) -> Path:
    """Return the hashed-copies directory for *kind* (``resume`` or ``board_memo``)."""
    return _work_products_dir(tenant_id) / "_hashes" / kind


# ---------------------------------------------------------------------------#
# Hashed-copy helpers (used by render_resume / render_memo)
# ---------------------------------------------------------------------------#


def _sha256_hex(text: str) -> str:
    """Return the SHA-256 hex digest of *text* (utf-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_hashed_copy(tenant_id: str, kind: str, content: str) -> Path | None:
    """Save a hashed copy of *content* under ``_hashes/{kind}/``.

    Writes ``{sha256}.md`` only when it does not already exist (identical
    content → same filename → no duplicate).  Returns the path or ``None``
    when the file already existed.
    """
    h = _sha256_hex(content)
    out_dir = _hashes_dir(tenant_id, kind)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{h}.md"
    if out_path.exists():
        return None
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _list_hashed_copies(tenant_id: str, kind: str) -> list[Path]:
    """Return sorted (by modification time) hashed copies for *kind*."""
    hdir = _hashes_dir(tenant_id, kind)
    if not hdir.is_dir():
        return []
    files = [p for p in hdir.iterdir() if p.is_file() and p.suffix == ".md"]
    files.sort(key=lambda p: p.stat().st_mtime)
    return files


# ---------------------------------------------------------------------------#
# Evidence pack
# ---------------------------------------------------------------------------#


def _configured_repo_path(tenant_id: str) -> str | None:
    """Return a configured local repo path for *tenant_id*, or ``None``.

    Resolution order:

    1. ``AEGIS_REPO_PATH`` env var (if it points to a dir with ``.git``).
    2. The first entry from the profile ``repositories`` field that
       resolves to an existing local directory with ``.git``.
    """
    env_path = os.getenv("AEGIS_REPO_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_dir() and (p / ".git").exists():
            return str(p)

    profile = get_latest_profile(tenant_id)
    if profile:
        repos_raw = (profile.get("repositories") or "").strip()
        for entry in repos_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            p2 = Path(entry)
            if p2.is_dir() and (p2 / ".git").exists():
                return str(p2)
    return None


def _git_observe_range(repo_path: str, max_commits: int = 20) -> dict[str, Any]:
    """Return a dict describing the local git-observe range for *repo_path*.

    Runs ``git log -n{max_commits} --format=%H%x09%ad%x09%s`` locally — no
    network, no remote fetch.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(
        [
            "git",
            "-C",
            repo_path,
            "log",
            f"-n{max_commits}",
            "--format=%H%x09%ad%x09%s",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return {
            "repo": os.path.basename(os.path.normpath(repo_path)),
            "error": "git log failed",
            "commits": [],
            "latest_sha": "",
            "count": 0,
        }

    commits: list[dict[str, str]] = []
    latest_sha = ""
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha, committed_at, subject = parts
        if not latest_sha:
            latest_sha = sha
        commits.append(
            {
                "sha": sha,
                "committed_at": committed_at,
                "subject": subject,
            }
        )

    return {
        "repo": os.path.basename(os.path.normpath(repo_path)),
        "commits": commits,
        "latest_sha": latest_sha,
        "count": len(commits),
    }


def _build_evidence_md(
    tenant_id: str,
    repo_path: str | None,
    git_info: dict[str, Any] | None,
) -> str:
    """Render the evidence pack markdown content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"# Evidence Pack — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        "## Git Observe Range",
        "",
    ]
    if repo_path and git_info and git_info.get("commits"):
        lines.append(f"**Repo:** {git_info['repo']}")
        lines.append(f"**Path:** {repo_path}")
        lines.append(f"**Latest SHA:** {git_info['latest_sha']}")
        lines.append(f"**Commits observed:** {git_info['count']}")
        lines.append("")
        lines.append("### Commits")
        lines.append("")
        for c in git_info["commits"]:
            lines.append(f"- {c['sha'][:12]} — {c['subject']} ({c['committed_at']})")
        lines.append("")
    else:
        lines.append("no git repo")
        lines.append("")

    lines.append("Do not act on this evidence without written principal approval.")
    lines.append("")
    return "\n".join(lines)


def evidence_pack(tenant_id: str) -> dict[str, Any]:
    """Write the evidence pack markdown for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Records the local git-observe range (latest commit SHA + count) when a
    repo path is configured (``AEGIS_REPO_PATH`` env or the profile
    ``repositories`` field), else records "no git repo".

    Writes ``work_products/{tenant_id}/evidence.md`` and returns
    ``{tenant_id, path, repo, latest_sha, count}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    repo_path = _configured_repo_path(tenant_id)
    git_info: dict[str, Any] | None = None
    if repo_path:
        git_info = _git_observe_range(repo_path)

    content = _build_evidence_md(tenant_id, repo_path, git_info)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "evidence.md"
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
        "repo": git_info["repo"] if git_info and git_info.get("commits") else "",
        "latest_sha": git_info["latest_sha"] if git_info else "",
        "count": git_info["count"] if git_info else 0,
    }


# ---------------------------------------------------------------------------#
# Resume diff
# ---------------------------------------------------------------------------#


def resume_diff(tenant_id: str) -> str:
    """Return a unified diff of the last two hashed resume copies.

    If fewer than two hashed copies exist, return an empty string.
    Does not require a consented profile — it only reads local files.
    """
    copies = _list_hashed_copies(tenant_id, "resume")
    if len(copies) < 2:
        return ""
    older, newer = copies[-2], copies[-1]
    old_lines = older.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = newer.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = unified_diff(
        old_lines,
        new_lines,
        fromfile=str(older.name),
        tofile=str(newer.name),
    )
    return "".join(diff)


# ---------------------------------------------------------------------------#
# Memo diff
# ---------------------------------------------------------------------------#


def memo_diff(tenant_id: str) -> str:
    """Return a unified diff of the last two hashed board-memo copies.

    If fewer than two hashed copies exist, return an empty string.
    Does not require a consented profile — it only reads local files.
    """
    copies = _list_hashed_copies(tenant_id, "board_memo")
    if len(copies) < 2:
        return ""
    older, newer = copies[-2], copies[-1]
    old_lines = older.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = newer.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = unified_diff(
        old_lines,
        new_lines,
        fromfile=str(older.name),
        tofile=str(newer.name),
    )
    return "".join(diff)
