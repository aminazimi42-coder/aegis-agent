"""Local CLI — print home, queue, and provider status (T84).

``python -m core.twin_local`` runs a zero-network local command that
prints the home markdown, pending vs approved-waiting queue counts,
and the current provider status.

The ``interview`` subcommand (T88) records a consented local profile
under the data root after explicit consent.  No secrets, card fields,
or network calls.

No ``urllib``, ``requests``, ``socket``, or ``http.client`` imports.
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m core.twin_local``.

    Supported commands:

    * ``status [TENANT_ID]``  — print home, queue, and provider status.
    * ``approve ACTION_ID TENANT_ID ACTOR_ID DIGEST`` — approve a proposed
      action after binding it to the exact envelope digest.
    * ``execute ACTION_ID TENANT_ID`` — execute an approved action.
    * ``interview TENANT_ID ROLE GOAL CONSENT`` — record a consented
      local profile under the data root.  ``CONSENT`` must be ``yes``;
      otherwise nothing is written and the command exits ``2``.

    The default command is ``status`` with the ``AEGIS_TENANT`` env var (or
    ``"default"``) as the tenant id.

    Unknown commands print to **stderr** and exit ``2``.  No ``urllib``,
    ``requests``, ``socket``, or ``http.client`` imports are used.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] == "status":
        return _status_cmd(argv[1:] if argv else [])

    command = argv[0]
    rest = argv[1:]

    if command == "approve":
        return _approve_cmd(rest)
    if command == "execute":
        return _execute_cmd(rest)
    if command == "interview":
        return _interview_cmd(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


def _status_cmd(rest: list[str]) -> int:
    """Print HOME, QUEUE, PROVIDER, and data root for *rest*."""
    import json

    from core.twin_local_view import (
        data_root,
        list_queue,
        provider_status,
        read_home,
    )

    if rest:
        tenant_id = rest[0]
    else:
        tenant_id = os.getenv("AEGIS_TENANT", "default")

    # --- HOME -----------------------------------------------------------
    # Check for a local consented profile written by ``interview``
    # (T88) before falling back to the SQLite-backed home renderer.
    local_profile = data_root() / tenant_id / "profile.json"
    if local_profile.is_file():
        try:
            data = json.loads(local_profile.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        role = data.get("role", "")
        goal = data.get("goal", "")
        home_md = f"# Home — {tenant_id}\n\n_role: {role}_\n\n_goal: {goal}_\n"
    else:
        try:
            home_md = read_home(tenant_id)
        except ValueError:
            home_md = "(no consented profile)"

    print("## HOME")
    print(home_md)

    # --- QUEUE ----------------------------------------------------------
    queue = list_queue(tenant_id)
    pending = len(queue["pending"])
    approved = len(queue["approved_waiting"])

    print()
    print("## QUEUE")
    print(f"pending: {pending}")
    print(f"approved_waiting: {approved}")

    # --- PROVIDER -------------------------------------------------------
    status = provider_status()

    print()
    print("## PROVIDER")
    print(f"kind: {status['kind']}")
    print(f"offline: {status['offline']}")

    # --- DATA ROOT ------------------------------------------------------
    root = data_root()
    print()
    print(f"data_root: {root}")

    return 0


def _approve_cmd(rest: list[str]) -> int:
    """Approve an action: ``approve ACTION_ID TENANT_ID ACTOR_ID DIGEST``."""
    if len(rest) != 4:
        print(
            "usage: approve ACTION_ID TENANT_ID ACTOR_ID DIGEST",
            file=sys.stderr,
        )
        return 2

    action_id, tenant_id, actor_id, digest = rest
    from core.twin_actions import approve

    result = approve(
        action_id,
        tenant_id,
        actor_id,
        expected_payload_sha256=digest,
    )
    print(result["status"])
    return 0


def _execute_cmd(rest: list[str]) -> int:
    """Execute an action: ``execute ACTION_ID TENANT_ID``."""
    if len(rest) != 2:
        print("usage: execute ACTION_ID TENANT_ID", file=sys.stderr)
        return 2

    action_id, tenant_id = rest
    from core.twin_actions import execute

    result = execute(action_id, tenant_id)
    print(result["status"])
    return 0


def _interview_cmd(rest: list[str]) -> int:
    """Record a consented local profile: ``interview TENANT_ID ROLE GOAL CONSENT``.

    Writes ``role``, ``goal``, and ``consented=true`` as JSON keys under
    ``{data_root}/{tenant_id}/profile.json``.  ``CONSENT`` must be
    ``"yes"`` (case-insensitive); otherwise nothing is written and the
    command exits ``2``.

    No secrets, card fields, or network calls.
    """
    import json

    from core.twin_local_view import data_root

    if len(rest) != 4:
        print(
            "usage: interview TENANT_ID ROLE GOAL CONSENT",
            file=sys.stderr,
        )
        return 2

    tenant_id, role, goal, consent = rest
    if consent.strip().lower() != "yes":
        return 2

    root = data_root()
    profile_dir = root / tenant_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        json.dumps(
            {"role": role, "goal": goal, "consented": True},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"profile: {profile_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
