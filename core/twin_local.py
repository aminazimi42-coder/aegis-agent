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
from datetime import datetime, timezone


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m core.twin_local``.

    Supported commands:

    * ``status [TENANT_ID]``  — print home, queue, and provider status.
    * ``approve ACTION_ID TENANT_ID ACTOR_ID DIGEST`` — approve a proposed
      action after binding it to the exact envelope digest.
    * ``execute ACTION_ID TENANT_ID`` — execute an approved action.
    * ``interview [TENANT_ID ROLE GOAL CONSENT]`` — record a consented
      local profile under the data root.  With four args, ``CONSENT``
      must be ``yes``; with no args, the four values are prompted on
      stdin (T89).  In either case, if consent is not ``yes``, nothing
      is written and the command exits ``2``.
    * ``propose TENANT_ID`` — insert one proposed ``twin_action`` whose
      payload includes ``role`` and ``goal`` read from the local
      consented ``profile.json`` (T90).  Writes nothing and exits ``2``
      when the profile is missing or ``consented`` is not ``true``.
      Does not approve or execute; no network, no card fields.
    * ``reject ACTION_ID TENANT_ID REASON`` — mark a proposed action as
      rejected with a short reason code from a small allow-list
      (``duplicate``, ``stale``, ``unsafe``, ``other``) (T99).  The
      reason is persisted on the action; the action is not executed.
      Exits ``2`` on an unknown action, tenant mismatch, or invalid
      reason.
    * ``verify TENANT_ID`` — recompute the payload digest for every
      pending action and print mismatch lines.  Exits ``1`` if any
      mismatch, else ``0`` (T96).
    * ``execute --dry-run ACTION_ID TENANT_ID`` — print what would run
      and write nothing; the action is not marked executed (T96).
    * ``search TENANT_ID TERM`` — grep-style scan under the tenant
      data root for ``.md``/``.json`` files matching *term*
      (case-insensitive).  Read-only (T100).
    * ``replay ACTION_ID TENANT_ID`` — write one markdown file under
      the tenant work-products directory listing the propose → approve
      → execute lifecycle if present.  Does not re-execute (T100).
    * ``export TENANT_ID OUT_PATH`` — pack the tenant's data-root
      folders into a local ``.tar.gz`` archive (T100).
    * ``import ARCHIVE_PATH`` — restore an archive into
      ``AEGIS_DATA_DIR``.  Never touches another tenant (T100).

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
    if command == "propose":
        return _propose_cmd(rest)
    if command == "reject":
        return _reject_cmd(rest)
    if command == "verify":
        return _verify_cmd(rest)
    if command == "search":
        return _search_cmd(rest)
    if command == "replay":
        return _replay_cmd(rest)
    if command == "export":
        return _export_cmd(rest)
    if command == "import":
        return _import_cmd(rest)

    if command == "evidence":
        return _evidence_cmd(rest)
    if command == "resume-diff":
        return _resume_diff_cmd(rest)
    if command == "memo-diff":
        return _memo_diff_cmd(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


def _age_from_created(created_at: str) -> str:
    """Return a short human-readable age string from an ISO timestamp.

    Examples: ``"3h12m"``, ``"2d5h"``, ``"45m"``.  Returns an empty
    string when *created_at* is empty.  Raises ``ValueError`` from
    :func:`datetime.fromisoformat` when the timestamp is malformed.
    """
    if not created_at:
        return ""
    dt = datetime.fromisoformat(created_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    if not parts:
        return "0m"
    return "".join(parts)


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
    pending = queue["pending"]
    approved = queue["approved_waiting"]

    print()
    print("## QUEUE")
    print(f"pending: {len(pending)}")
    print(f"approved_waiting: {len(approved)}")

    # T94 — show payload_sha256 for each pending item when present.
    # T98 — also show action_id, title, age, digest, and specialist on a
    # readable line; keep the ``pending_digest:`` line for compatibility.
    for item in pending:
        action_id = item.get("action_id", "")
        title = item.get("title", "")
        digest = item.get("payload_sha256") or ""
        if digest:
            print(f"pending_digest: {action_id} {digest}")
        created = item.get("created_at", "")
        age = ""
        if created:
            try:
                age = _age_from_created(created)
            except (ValueError, TypeError):
                age = ""
        specialist = item.get("kind", "")
        if specialist and ":" in specialist:
            specialist = specialist.rsplit(":", 1)[0]
        print(
            f"pending: {action_id} {title!r} age={age} "
            f"digest={digest} specialist={specialist}"
        )

    # --- PROVIDER -------------------------------------------------------
    status = provider_status()

    print()
    print("## PROVIDER")
    print(f"kind: {status['kind']}")
    print(f"offline: {status['offline']}")

    # --- DEAD-MAN (T102) ------------------------------------------------
    try:
        from core.t102_local_guards import dead_man_warning

        warning = dead_man_warning(tenant_id)
        if warning:
            print()
            print(f"WARNING: {warning}")
    except Exception:  # pragma: no cover — never break status on guard error
        pass

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
    from core.twin_audit import append_audit

    result = approve(
        action_id,
        tenant_id,
        actor_id,
        expected_payload_sha256=digest,
    )
    append_audit(tenant_id, "approve", action_id)
    print(result["status"])
    return 0


def _execute_cmd(rest: list[str]) -> int:
    """Execute an action: ``execute [--dry-run] ACTION_ID TENANT_ID [CONFIRM]``.

    With ``--dry-run`` (T96): prints what would run and writes nothing;
    the action is not marked executed and no audit line is appended.

    **T97 — typed confirm for L2/L3:**  When the action's risk level is
    ``L2`` or ``L3``, an extra ``CONFIRM`` CLI argument is required and
    must equal the literal string ``"CONFIRM"``.  If it is missing or
    wrong, nothing is written and the command exits ``2``.  ``L0`` and
    ``L1`` actions are unchanged — no ``CONFIRM`` argument is needed.
    The digest lock in :func:`core.twin_actions.execute` stays in force.
    """
    dry_run = False
    if rest and rest[0] == "--dry-run":
        dry_run = True
        rest = rest[1:]

    if len(rest) < 2:
        print("usage: execute [--dry-run] ACTION_ID TENANT_ID [CONFIRM]", file=sys.stderr)
        return 2

    action_id, tenant_id = rest[:2]
    extra = rest[2:]

    # Load the action to determine its risk level.
    from core.twin_actions import _load_action
    from core.twin_risk import attach_risk

    action = _load_action(action_id)
    if action is None:
        print(f"unknown action: {action_id}", file=sys.stderr)
        return 1
    if action["tenant_id"] != tenant_id:
        print("tenant mismatch", file=sys.stderr)
        return 1

    risked = attach_risk(action)
    risk_level = risked.get("risk_level", "L0")

    # T97 — L2/L3 require a typed CONFIRM argument equal to "CONFIRM".
    if risk_level in ("L2", "L3"):
        confirm = extra[0] if extra else ""
        if confirm != "CONFIRM":
            print(
                f"confirm required for {risk_level} action: execute [...] CONFIRM",
                file=sys.stderr,
            )
            return 2

    if dry_run:
        print(f"would execute: {action_id}")
        print(f"  kind: {action.get('kind', '')}")
        print(f"  title: {action.get('title', '')}")
        print(f"  status: {action.get('status', '')}")
        print(f"  risk: {risk_level}")
        print("  writes: nothing")
        return 0

    from core.twin_actions import execute
    from core.twin_audit import append_audit

    result = execute(action_id, tenant_id)
    append_audit(tenant_id, "execute", action_id)
    # T98 — print a receipt line: action_id + digest + executed.
    digest = result.get("payload_sha256") or result.get("approved_payload_sha256") or ""
    print(f"receipt: {action_id} digest={digest} executed")
    print(result["status"])
    return 0


def _verify_cmd(rest: list[str]) -> int:
    """Verify pending action digests: ``verify TENANT_ID`` (T96).

    Recompute the payload digest for every pending action and print one
    mismatch line per row whose stored ``payload_sha256`` differs from the
    freshly recomputed digest.  Exits ``1`` if any mismatch, else ``0``.
    """
    if len(rest) != 1:
        print("usage: verify TENANT_ID", file=sys.stderr)
        return 2

    tenant_id = rest[0]
    from core.twin_actions import _action_digest, list_actions

    actions = list_actions(tenant_id)
    pending = [a for a in actions if a.get("status") == "proposed"]
    mismatches = 0
    for a in pending:
        stored = a.get("payload_sha256") or ""
        recomputed = _action_digest(a)
        if stored != recomputed:
            print(f"mismatch: {a['action_id']} stored={stored} recomputed={recomputed}")
            mismatches += 1
    if mismatches:
        print(f"verify: {mismatches} mismatch(es) for tenant {tenant_id}")
        return 1
    print(f"verify: ok ({len(pending)} pending for tenant {tenant_id})")
    return 0


def _interview_cmd(rest: list[str]) -> int:
    """Record a consented local profile.

    Two forms:

    * **Batch** — ``interview TENANT_ID ROLE GOAL CONSENT`` (T88).
    * **Interactive** — ``interview`` with no extra args prompts on
      *stdin* for ``tenant``, ``role``, ``goal``, and ``consent``
      (T89).  Each value is read as a single line from ``stdin``.

    In both forms ``CONSENT`` must be ``"yes"`` (case-insensitive);
    otherwise nothing is written and the command exits ``2``.

    Writes ``role``, ``goal``, and ``consented=true`` as JSON keys
    under ``{data_root}/{tenant_id}/profile.json``.

    No secrets, card fields, or network calls.
    """
    import json

    from core.twin_local_view import data_root

    if len(rest) == 4:
        tenant_id, role, goal, consent = rest
    elif len(rest) == 0:
        tenant_id = input("tenant: ").strip()
        role = input("role: ").strip()
        goal = input("goal: ").strip()
        consent = input("consent: ").strip()
    else:
        print(
            "usage: interview [TENANT_ID ROLE GOAL CONSENT]",
            file=sys.stderr,
        )
        return 2

    if consent.lower() != "yes":
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


def _propose_cmd(rest: list[str]) -> int:
    """Insert one proposed twin_action from the local consented profile (T90).

    Usage: ``propose TENANT_ID``.  Reads ``{data_root}/{tenant_id}/profile.json``
    and — when it exists and ``consented`` is ``true`` — inserts exactly one
    proposed action whose payload includes ``role`` and ``goal``.  The action
    is inserted via :func:`core.twin_actions.insert_specialist_proposal`
    so the canonical envelope digest and ``payload_sha256`` are computed
    consistently with T56/T60.

    Writes nothing and exits ``2`` when ``profile.json`` is missing, cannot
    be parsed, or ``consented`` is not ``true``.  Does **not** approve or
    execute.  No network, no card fields.
    """
    import json

    from core.twin_actions import insert_specialist_proposal
    from core.twin_audit import append_audit
    from core.twin_local_view import data_root

    if len(rest) != 1:
        print("usage: propose TENANT_ID", file=sys.stderr)
        return 2

    tenant_id = rest[0]
    root = data_root()
    profile_path = root / tenant_id / "profile.json"
    if not profile_path.is_file():
        return 2
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 2
    if data.get("consented") is not True:
        return 2

    role = data.get("role", "")
    goal = data.get("goal", "")
    title = f"Propose from profile — role: {role}, goal: {goal}"
    try:
        result = insert_specialist_proposal(
            tenant_id=tenant_id,
            agent_name="twin_local",
            title=title,
            payload={"role": role, "goal": goal},
        )
    except ValueError as exc:
        print(f"propose error: {exc}", file=sys.stderr)
        return 2
    append_audit(tenant_id, "propose", result["action_id"])
    # T94 — print payload_sha256 on its own line so ``aegis approve``
    # can read it without parsing JSON.
    digest = result.get("payload_sha256") or ""
    if digest:
        print(f"payload_sha256: {digest}")
    print(json.dumps(result, default=str))
    return 0


def _reject_cmd(rest: list[str]) -> int:
    """Reject an action: ``reject ACTION_ID TENANT_ID REASON`` (T99).

    ``REASON`` must be one of the allow-list codes (``duplicate``,
    ``stale``, ``unsafe``, ``other``).  The reason is persisted on the
    action row and the status is set to ``rejected``.  The action is
    **not** executed.

    Exits ``2`` on a usage error, unknown action, tenant mismatch, or
    invalid reason.
    """
    if len(rest) != 3:
        print("usage: reject ACTION_ID TENANT_ID REASON", file=sys.stderr)
        return 2

    action_id, tenant_id, reason = rest
    from core.twin_actions import reject
    from core.twin_audit import append_audit

    try:
        result = reject(action_id, tenant_id, reason=reason)
    except ValueError as exc:
        print(f"reject error: {exc}", file=sys.stderr)
        return 2

    append_audit(tenant_id, "reject", action_id)
    print(result["status"])
    return 0


def _search_cmd(rest: list[str]) -> int:
    """Search tenant files: ``search TENANT_ID TERM`` (T100).

    Greps ``.md`` and ``.json`` files under the tenant's data-root
    directories for *term* (case-insensitive).  Prints each matching
    path on its own line.  Read-only.
    """
    if len(rest) != 2:
        print("usage: search TENANT_ID TERM", file=sys.stderr)
        return 2

    tenant_id, term = rest
    from core.twin_local_recall import search

    matches = search(tenant_id, term)
    for m in matches:
        print(m)
    return 0


def _replay_cmd(rest: list[str]) -> int:
    """Replay an action lifecycle: ``replay ACTION_ID TENANT_ID`` (T100).

    Writes one markdown file under the tenant work-products directory
    listing the propose → approve → execute lifecycle if present.  Does
    not re-execute.
    """
    if len(rest) != 2:
        print("usage: replay ACTION_ID TENANT_ID", file=sys.stderr)
        return 2

    action_id, tenant_id = rest
    from core.twin_local_recall import replay

    try:
        result = replay(action_id, tenant_id)
    except ValueError as exc:
        print(f"replay error: {exc}", file=sys.stderr)
        return 2
    print(result["path"])
    return 0


def _export_cmd(rest: list[str]) -> int:
    """Export tenant data: ``export TENANT_ID OUT_PATH`` (T100).

    Packs the tenant's data-root folders into a local ``.tar.gz`` archive.
    """
    if len(rest) != 2:
        print("usage: export TENANT_ID OUT_PATH", file=sys.stderr)
        return 2

    tenant_id, out_path = rest
    from core.twin_local_recall import export_tenant

    result = export_tenant(tenant_id, out_path)
    print(result["archive"])
    return 0


def _import_cmd(rest: list[str]) -> int:
    """Import an archive: ``import ARCHIVE_PATH`` (T100).

    Restores the archive into ``AEGIS_DATA_DIR``.  Never touches another
    tenant.
    """
    if len(rest) != 1:
        print("usage: import ARCHIVE_PATH", file=sys.stderr)
        return 2

    archive_path = rest[0]
    from core.twin_local_recall import import_archive

    try:
        result = import_archive(archive_path)
    except (ValueError, OSError) as exc:
        print(f"import error: {exc}", file=sys.stderr)
        return 2
    print(result["data_root"])
    return 0


def _evidence_cmd(rest: list[str]) -> int:
    """Write the evidence pack: ``evidence TENANT_ID`` (T101).

    Records the local git-observe range if a repo path is configured,
    else records "no git repo".
    """
    if len(rest) != 1:
        print("usage: evidence TENANT_ID", file=sys.stderr)
        return 2

    tenant_id = rest[0]
    from core.twin_work_history import evidence_pack

    try:
        result = evidence_pack(tenant_id)
    except ValueError as exc:
        print(f"evidence error: {exc}", file=sys.stderr)
        return 2
    print(result["path"])
    return 0


def _resume_diff_cmd(rest: list[str]) -> int:
    """Print a unified diff of the last two hashed resume copies (T101).

    If fewer than two hashed copies exist, prints nothing and exits 0.
    """
    if len(rest) != 1:
        print("usage: resume-diff TENANT_ID", file=sys.stderr)
        return 2

    tenant_id = rest[0]
    from core.twin_work_history import resume_diff

    diff = resume_diff(tenant_id)
    if diff:
        print(diff, end="")
    return 0


def _memo_diff_cmd(rest: list[str]) -> int:
    """Print a unified diff of the last two hashed board-memo copies (T101).

    If fewer than two hashed copies exist, prints nothing and exits 0.
    """
    if len(rest) != 1:
        print("usage: memo-diff TENANT_ID", file=sys.stderr)
        return 2

    tenant_id = rest[0]
    from core.twin_work_history import memo_diff

    diff = memo_diff(tenant_id)
    if diff:
        print(diff, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
