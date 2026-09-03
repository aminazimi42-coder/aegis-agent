#!/usr/bin/env python3
"""Aegis Agent CLI — thin command-line wrappers around core twin flows.

Usage::

    python -m cli audio-task --tenant <id> --file <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _audio_task(tenant_id: str, file_path: str) -> dict[str, Any]:
    """Run the T34 audio sidecar → proposed task flow."""
    from core.twin_audio_task import from_audio

    return from_audio(tenant_id, file_path)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Aegis CLI."""
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="Aegis Agent CLI — twin workflow commands.",
    )
    sub = parser.add_subparsers(dest="command")

    # audio-task
    audio_parser = sub.add_parser(
        "audio-task",
        help="Turn a local audio file + .txt sidecar into one proposed task.",
    )
    audio_parser.add_argument("--tenant", required=True, help="Tenant identifier.")
    audio_parser.add_argument(
        "--file",
        required=True,
        help="Path to the audio file (a sibling .txt sidecar is required).",
    )

    args = parser.parse_args(argv)

    if args.command == "audio-task":
        try:
            result = _audio_task(args.tenant, args.file)
            print(json.dumps(result, indent=2))
            return 0
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
