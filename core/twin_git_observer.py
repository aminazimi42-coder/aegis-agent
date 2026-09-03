"""Local git observer for the cognitive twin.

Scans a *local* git working copy without touching the network and feeds each
commit into the twin evolution loop (``ingest_event`` + ``evolve``).

No GitHub API, no remote fetch — only ``git log`` over an existing repo path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event, list_events
from core.twin_evolution import evolve
from core.twin_interview import get_latest_profile


def _repo_name(repo_path: str) -> str:
    """Return a stable display name for *repo_path* (basename, no slash)."""
    return os.path.basename(os.path.normpath(repo_path)) or repo_path


def _already_seen_shas(tenant_id: str) -> set[str]:
    """Return the set of commit SHAs already stored in twin_events payload."""
    seen: set[str] = set()
    for ev in list_events(tenant_id, limit=1000):
        if ev.get("source") != "git" or ev.get("kind") != "commit":
            continue
        payload = ev.get("payload") or {}
        sha = payload.get("sha")
        if sha:
            seen.add(sha)
    return seen


def observe_repo(
    tenant_id: str,
    repo_path: str,
    *,
    max_commits: int = 20,
) -> dict[str, Any]:
    """Observe a local git repo and feed new commits to the twin.

    Requires a consented twin profile (raises ``ValueError`` otherwise) and a
    ``.git`` directory under *repo_path* (raises ``ValueError`` otherwise).

    Returns ``{tenant_id, repo, ingested, skipped, latest_sha}`` where
    ``ingested`` counts only *new* SHAs (de-duplicated against prior events).
    """
    # Consent gate — must have a committed twin profile.
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    repo = Path(repo_path)
    if not repo.is_dir() or not (repo / ".git").exists():
        raise ValueError("not a git repo")

    repo_name = _repo_name(str(repo))

    # Local-only git log: no network, no remote fetch.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            f"-n{max_commits}",
            "--format=%H%x09%ad%x09%s",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        # Non-zero git log — treat as not a usable repo.
        raise ValueError("not a git repo")

    already_seen = _already_seen_shas(tenant_id)
    ingested = 0
    skipped = 0
    latest_sha = ""

    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha, committed_at, subject = parts[0], parts[1], parts[2]
        if not latest_sha:
            latest_sha = sha
        if sha in already_seen:
            skipped += 1
            continue
        event = ingest_event(
            tenant_id=tenant_id,
            source="git",
            kind="commit",
            payload={
                "repo": repo_name,
                "sha": sha,
                "subject": subject,
                "committed_at": committed_at,
            },
        )
        evolve(tenant_id, event)
        already_seen.add(sha)
        ingested += 1

    return {
        "tenant_id": tenant_id,
        "repo": repo_name,
        "ingested": ingested,
        "skipped": skipped,
        "latest_sha": latest_sha,
    }
