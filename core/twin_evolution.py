"""Deterministic twin evolution and weekly digest.

The evolution loop is *not* a live LLM — it applies deterministic rules to
structured work events and produces a new versioned ``TwinProfile`` only
when a layer actually changes.  The weekly digest summarises recent
activity without any network calls.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_events import Event, list_events
from core.twin_interview import get_latest_profile
from core.twin_schema import compute_fingerprint

_evolve_lock = threading.Lock()


# ---------------------------------------------------------------------------#
# Layer helpers
# ---------------------------------------------------------------------------#

_LAYER_FIELDS: tuple[str, ...] = (
    "role",
    "decision_style",
    "tools",
    "risk_posture",
    "work_ethics",
    "repositories",
)


def _current_layers(profile: dict[str, Any]) -> dict[str, Any]:
    """Extract the layer dict from a profile returned by get_latest_profile."""
    return {f: profile.get(f, "") for f in _LAYER_FIELDS}


def _persist_profile(
    tenant_id: str,
    version: int,
    layers: dict[str, Any],
) -> dict[str, Any]:
    """Insert a new versioned profile row and return it as a dict."""
    profile_id = f"profile-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    fp = compute_fingerprint(layers)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO twin_profiles "
            "(profile_id, tenant_id, version, consent, "
            "fingerprint, layers, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                profile_id,
                tenant_id,
                version,
                1,
                fp,
                json.dumps(layers),
                now,
                now,
            ),
        )
    return {
        "profile_id": profile_id,
        "tenant_id": tenant_id,
        "version": version,
        "consent": True,
        "fingerprint": fp,
        "created_at": now,
        "updated_at": now,
        **layers,
    }


# ---------------------------------------------------------------------------#
# Evolve
# ---------------------------------------------------------------------------#

def evolve(tenant_id: str, event: dict[str, Any] | Event) -> dict[str, Any]:
    """Apply ``event`` to the latest twin profile using deterministic rules.

    Rules:
      - source git + kind commit → append ``payload.repo`` to repositories (unique)
      - kind meeting → set tools hint "calendar" if missing
      - ``payload.risk`` in {low,medium,high} → set risk_posture
      - ``payload.role`` → set role unless ``overwrite_role`` is False

    If no layer changes, the previous profile is returned unchanged.
    """
    if isinstance(event, Event):
        event = event.to_dict()

    with _evolve_lock:
        profile = get_latest_profile(tenant_id)
        if profile is None:
            raise ValueError("no consented profile")

        layers = _current_layers(profile)
        changed = False

        source = event.get("source", "")
        kind = event.get("kind", "")
        payload = event.get("payload") or {}

        # Rule 1: git commit → append repo name (unique)
        if source == "git" and kind == "commit":
            repo = payload.get("repo", "")
            if repo:
                current_repos = layers["repositories"]
                if current_repos:
                    repo_list = [
                        r.strip()
                        for r in current_repos.split(",")
                        if r.strip()
                    ]
                else:
                    repo_list = []
                if repo not in repo_list:
                    repo_list.append(repo)
                new_repos = ", ".join(repo_list)
                if new_repos != current_repos:
                    layers["repositories"] = new_repos
                    changed = True

        # Rule 2: meeting → tools hint "calendar"
        if kind == "meeting":
            current_tools = layers.get("tools", "")
            if "calendar" not in current_tools:
                if current_tools:
                    layers["tools"] = current_tools + ", calendar"
                else:
                    layers["tools"] = "calendar"
                changed = True

        # Rule 3: risk posture
        risk = payload.get("risk")
        if risk in ("low", "medium", "high"):
            if layers.get("risk_posture", "") != risk:
                layers["risk_posture"] = risk
                changed = True

        # Rule 4: role (do not overwrite unless overwrite_role=True)
        role = payload.get("role")
        if role:
            if payload.get("overwrite_role") is True or not layers.get("role"):
                if layers.get("role", "") != role:
                    layers["role"] = role
                    changed = True

        if not changed:
            return profile

        new_version = profile["version"] + 1
        return _persist_profile(tenant_id, new_version, layers)


# ---------------------------------------------------------------------------#
# Weekly digest
# ---------------------------------------------------------------------------#

def weekly_digest(tenant_id: str) -> dict[str, Any]:
    """Produce a deterministic weekly digest for ``tenant_id``.

    No network / LLM calls — everything is derived from stored events and
    the latest profile.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    events = list_events(tenant_id, limit=50)

    # Collect unique repos from git-commit events.
    repos: list[str] = []
    for ev in events:
        p = ev.get("payload") or {}
        repo = p.get("repo")
        if repo and repo not in repos:
            repos.append(repo)

    # Derive highlights deterministically.
    highlights: list[str] = []
    commit_count = sum(1 for e in events if e["kind"] == "commit")
    meeting_count = sum(1 for e in events if e["kind"] == "meeting")
    note_count = sum(1 for e in events if e["kind"] == "note")

    if repos:
        highlights.append(f"Active repos: {', '.join(repos)}")
    if commit_count:
        highlights.append(f"Commits this week: {commit_count}")
    if meeting_count:
        highlights.append(f"Meetings this week: {meeting_count}")
    if note_count:
        highlights.append(f"Notes captured: {note_count}")
    if not highlights:
        highlights.append("No significant activity this week")

    last_event_at = events[0]["created_at"] if events else ""

    return {
        "tenant_id": tenant_id,
        "profile_version": profile["version"],
        "event_count": len(events),
        "repos": repos,
        "last_event_at": last_event_at,
        "highlights": highlights,
    }
