"""Local twin CLI — drive interview, approve actions, and render work products.

Usage::

    python -m tools.twin_cli status
    python tools/twin_cli.py interview-start --tenant <ID>
    python tools/twin_cli.py interview-answer --session <ID> --question <ID> --text <TEXT>
    python tools/twin_cli.py interview-commit --session <ID> --consent {true,false}
    python tools/twin_cli.py actions-propose --tenant <ID>
    python tools/twin_cli.py actions-approve --action-id <ID>
    python tools/twin_cli.py actions-execute --action-id <ID>
    python tools/twin_cli.py render --tenant <ID>
    python tools/twin_cli.py brief-morning --tenant <ID>
    python tools/twin_cli.py email-triage --tenant <ID> --dir <PATH>
    python tools/twin_cli.py brief-meetings --tenant <ID>
    python tools/twin_cli.py followups --tenant <ID>
    python tools/twin_cli.py delegate --tenant <ID>

Each subcommand prints a JSON object to stdout (``json.dumps(default=str)``)
and exits 0 on success.  On ``ValueError`` or ``PermissionError`` the CLI
prints ``{"error": str}`` to stdout and exits 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------#
# sys.path bootstrap — allow running ``python tools/twin_cli.py`` directly
# without a pre-configured PYTHONPATH.
# ---------------------------------------------------------------------------#
if "core" not in sys.modules:
    _repo_root = str(Path(__file__).resolve().parent.parent)
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

# ---------------------------------------------------------------------------#
# Command handlers — each returns a JSON-serialisable dict or raises.
# ---------------------------------------------------------------------------#


def _cmd_status(_args: argparse.Namespace) -> dict[str, Any]:
    from core.platform_status import platform_status

    return platform_status()


def _cmd_interview_start(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_interview import start_session

    return start_session(args.tenant)


def _cmd_interview_answer(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_interview import answer

    return answer(args.session, args.question, args.text)


def _cmd_interview_commit(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_interview import commit

    return commit(args.session, args.consent)


def _cmd_actions_propose(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_actions import propose_actions

    return {"actions": propose_actions(args.tenant)}


def _cmd_actions_approve(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_actions import approve

    return approve(args.action_id)


def _cmd_actions_execute(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_actions import execute

    return execute(args.action_id)


def _cmd_render(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_work_products import render

    return render(args.tenant)


def _cmd_calendar_ics(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_calendar import ingest_ics

    return ingest_ics(args.tenant, args.path)


def _cmd_brief_morning(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_morning_brief import render_brief

    return render_brief(args.tenant)


def _cmd_email_triage(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_email_triage import triage

    return triage(args.tenant, args.dir)


def _cmd_brief_meetings(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_meeting_brief import render_meetings

    return render_meetings(args.tenant)


def _cmd_followups(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_followups import render_followups

    return render_followups(args.tenant)


def _cmd_delegate(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_delegate_pack import render_pack

    return render_pack(args.tenant)


def _cmd_decision_record(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_decisions import record

    return record(args.tenant, args.title, args.decision, args.reason)


def _cmd_decision_list(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_decisions import list_decisions

    decisions = list_decisions(args.tenant, query=args.query or "")
    return {"decisions": decisions, "count": len(decisions)}


def _cmd_style_lock(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_style_lock import lock_style

    return lock_style(args.tenant, args.dir)


def _cmd_pr_review(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_pr_review import review_diff

    return review_diff(args.tenant, args.diff)


def _cmd_expenses(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_expenses import ingest_receipts

    return ingest_receipts(args.tenant, args.dir)


def _cmd_focus_block(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_focus_block import create_block

    return create_block(
        args.tenant,
        args.start,
        duration_min=args.duration,
        title=args.title,
    )


def _cmd_travel(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_travel_pack import render_pack

    return render_pack(args.tenant, docs_dir=args.dir or "")


def _cmd_team_inbox(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_team_inbox import triage

    return triage(args.tenant, args.file)


def _cmd_transcript_task(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_transcript_task import from_transcript

    return from_transcript(args.tenant, args.file)


def _cmd_board_memo(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_board_memo import render_memo

    return render_memo(args.tenant)


def _cmd_resume(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_resume_pack import render_resume

    return render_resume(args.tenant)


def _cmd_email_send(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_email_send import send_approved

    return send_approved(args.tenant, args.action)


def _cmd_schedule(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_scheduler import schedule

    return schedule(
        args.tenant,
        args.title,
        args.due,
        timezone_=args.timezone,
    )


def _cmd_schedule_tick(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_scheduler import tick

    due = tick(args.now)
    return {"due": due, "count": len(due)}


def _cmd_goal_plan(args: argparse.Namespace) -> dict[str, Any]:
    from core.twin_goal_plan import plan_goal

    return plan_goal(args.tenant, args.text)


# ---------------------------------------------------------------------------#
# Argument parsing
# ---------------------------------------------------------------------------#


def _str2bool(value: str) -> bool:
    """Parse a boolean from a string (accepts true/false/1/0)."""
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean: {value!r}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twin_cli",
        description="Local twin CLI — interview, approve, and render.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Print platform status.")

    # interview-start
    p = sub.add_parser("interview-start", help="Start a new interview session.")
    p.add_argument("--tenant", required=True)

    # interview-answer
    p = sub.add_parser("interview-answer", help="Answer the next interview question.")
    p.add_argument("--session", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--text", required=True)

    # interview-commit
    p = sub.add_parser("interview-commit", help="Commit a completed interview.")
    p.add_argument("--session", required=True)
    p.add_argument(
        "--consent",
        type=_str2bool,
        required=True,
    )

    # actions-propose
    p = sub.add_parser("actions-propose", help="Propose work items for a tenant.")
    p.add_argument("--tenant", required=True)

    # actions-approve
    p = sub.add_parser("actions-approve", help="Approve a proposed action.")
    p.add_argument("--action-id", required=True)

    # actions-execute
    p = sub.add_parser("actions-execute", help="Execute an approved action.")
    p.add_argument("--action-id", required=True)

    # render
    p = sub.add_parser("render", help="Render local work-product files.")
    p.add_argument("--tenant", required=True)

    # calendar-ics
    p = sub.add_parser("calendar-ics", help="Ingest a local .ics calendar file.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--path", required=True)

    # brief-morning
    p = sub.add_parser("brief-morning", help="Render a one-page morning brief.")
    p.add_argument("--tenant", required=True)

    # email-triage
    p = sub.add_parser("email-triage", help="Triage a folder of .eml files.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--dir", required=True)

    # brief-meetings
    p = sub.add_parser("brief-meetings", help="Render per-meeting briefs.")
    p.add_argument("--tenant", required=True)

    # followups
    p = sub.add_parser("followups", help="Render the follow-up list.")
    p.add_argument("--tenant", required=True)

    # delegate
    p = sub.add_parser("delegate", help="Render the delegate pack.")
    p.add_argument("--tenant", required=True)

    # decision-record
    p = sub.add_parser("decision-record", help="Record a yes/no decision.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--decision", required=True, choices=["yes", "no"])
    p.add_argument("--reason", required=True)

    # decision-list
    p = sub.add_parser("decision-list", help="List recorded decisions.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--query", default="")

    # style-lock
    p = sub.add_parser("style-lock", help="Lock writing style from local text samples.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--dir", required=True)

    # pr-review
    p = sub.add_parser("pr-review", help="Turn a local diff into PR review notes.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--diff", required=True)

    # expenses
    p = sub.add_parser("expenses", help="Ingest a folder of receipt .txt files into expense notes.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--dir", required=True)

    # focus-block
    p = sub.add_parser("focus-block", help="Create a local focus-block hold (markdown + .ics).")
    p.add_argument("--tenant", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--title", default="Focus")

    # travel
    p = sub.add_parser("travel", help="Render a one-page travel pack from calendar + docs.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--dir", default="")

    # team-inbox
    p = sub.add_parser("team-inbox", help="Triage a local team-chat export into a markdown page.")
    p.add_argument("--tenant", required=True)
    p.add_argument("--file", required=True)

    # transcript-task
    p = sub.add_parser(
        "transcript-task",
        help="Turn a local transcript .txt into one proposed twin action.",
    )
    p.add_argument("--tenant", required=True)
    p.add_argument("--file", required=True)

    # board-memo
    p = sub.add_parser("board-memo", help="Render a one-page board weekly memo.")
    p.add_argument("--tenant", required=True)

    # resume
    p = sub.add_parser("resume", help="Render a one-page principal resume.")
    p.add_argument("--tenant", required=True)

    # email-send
    p = sub.add_parser(
        "email-send",
        help="Send an approved email draft to the local outbox only.",
    )
    p.add_argument("--tenant", required=True)
    p.add_argument("--action", required=True)

    # schedule
    p = sub.add_parser(
        "schedule",
        help="Schedule a durable commitment job (T41).",
    )
    p.add_argument("--tenant", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--due", required=True, help="Due-at ISO-8601 timestamp.")
    p.add_argument("--timezone", default="UTC")

    # schedule-tick
    p = sub.add_parser(
        "schedule-tick",
        help="Tick the scheduler — mark due jobs.",
    )
    p.add_argument("--now", default=None, help="Override now ISO-8601 timestamp.")

    # goal-plan
    p = sub.add_parser(
        "goal-plan",
        help="Turn goal text into an ordered proposed-action plan (T42).",
    )
    p.add_argument("--tenant", required=True)
    p.add_argument("--text", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point — parse args, dispatch, print JSON, and return exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = {
        "status": _cmd_status,
        "interview-start": _cmd_interview_start,
        "interview-answer": _cmd_interview_answer,
        "interview-commit": _cmd_interview_commit,
        "actions-propose": _cmd_actions_propose,
        "actions-approve": _cmd_actions_approve,
        "actions-execute": _cmd_actions_execute,
        "render": _cmd_render,
        "calendar-ics": _cmd_calendar_ics,
        "brief-morning": _cmd_brief_morning,
        "email-triage": _cmd_email_triage,
        "brief-meetings": _cmd_brief_meetings,
        "followups": _cmd_followups,
        "delegate": _cmd_delegate,
        "decision-record": _cmd_decision_record,
        "decision-list": _cmd_decision_list,
        "style-lock": _cmd_style_lock,
        "pr-review": _cmd_pr_review,
        "expenses": _cmd_expenses,
        "focus-block": _cmd_focus_block,
        "travel": _cmd_travel,
        "team-inbox": _cmd_team_inbox,
        "transcript-task": _cmd_transcript_task,
        "board-memo": _cmd_board_memo,
        "resume": _cmd_resume,
        "email-send": _cmd_email_send,
        "schedule": _cmd_schedule,
        "schedule-tick": _cmd_schedule_tick,
        "goal-plan": _cmd_goal_plan,
    }[args.command]

    try:
        result = handler(args)
    except (ValueError, PermissionError) as exc:
        print(json.dumps({"error": str(exc)}, default=str))
        return 2

    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
