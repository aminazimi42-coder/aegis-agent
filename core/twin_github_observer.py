"""GitHub PAT read-only observer for the cognitive twin.

Fetches commits from a public or private GitHub repository using a
Personal Access Token (``AEGIS_GITHUB_TOKEN``) and feeds each new commit
into the twin evolution loop (``ingest_event`` + ``evolve``).

No live network in tests — all HTTP calls go through ``urllib.request.urlopen``
which tests monkeypatch.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from core.twin_events import ingest_event, list_events
from core.twin_evolution import evolve
from core.twin_interview import get_latest_profile


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


def observe_github(
    tenant_id: str,
    repo: str,
    *,
    max_commits: int = 20,
) -> dict[str, Any]:
    """Observe a GitHub repo via the REST API and feed new commits to the twin.

    Requires:
      - A consented twin profile (raises ``ValueError("no consented profile")``).
      - ``AEGIS_GITHUB_TOKEN`` env var (raises ``ValueError("missing github token")``).

    Returns ``{tenant_id, repo, ingested, skipped}``.
    """
    # Consent gate — must have a committed twin profile.
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    token = os.environ.get("AEGIS_GITHUB_TOKEN")
    if not token:
        raise ValueError("missing github token")

    url = (
        f"https://api.github.com/repos/{repo}/commits"
        f"?per_page={max_commits}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, RuntimeError):
        raise ValueError("github observe failed") from None

    if not isinstance(body, list):
        raise ValueError("github observe failed")

    already_seen = _already_seen_shas(tenant_id)
    ingested = 0
    skipped = 0

    for item in body:
        sha = item.get("sha", "")
        if not sha:
            skipped += 1
            continue
        # Extract commit subject from the nested commit.message.
        commit_info = item.get("commit") or {}
        message = commit_info.get("message", "")
        subject = message.split("\n", 1)[0] if message else ""
        if sha in already_seen:
            skipped += 1
            continue
        event = ingest_event(
            tenant_id=tenant_id,
            source="git",
            kind="commit",
            payload={
                "repo": repo,
                "sha": sha,
                "subject": subject,
            },
        )
        evolve(tenant_id, event)
        already_seen.add(sha)
        ingested += 1

    return {
        "tenant_id": tenant_id,
        "repo": repo,
        "ingested": ingested,
        "skipped": skipped,
    }
