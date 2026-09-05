"""Local CLI — print home, queue, and provider status (T84).

``python -m core.twin_local`` runs a zero-network local command that
prints the home markdown, pending vs approved-waiting queue counts,
and the current provider status.

No ``urllib``, ``requests``, ``socket``, or ``http.client`` imports.
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m core.twin_local``.

    Default command is ``status``.  An optional second argument supplies
    the tenant id (default ``"default"`` or ``AEGIS_TENANT``).

    Prints three sections — **HOME**, **QUEUE**, **PROVIDER** — then
    returns ``0``.  No network libraries are used.
    """
    if argv is None:
        argv = sys.argv[1:]

    command = "status"
    tenant_id = os.getenv("AEGIS_TENANT", "default")

    if argv:
        if argv[0] == "status":
            if len(argv) > 1:
                tenant_id = argv[1]
        else:
            tenant_id = argv[0]

    if command != "status":
        print(f"unknown command: {command}", file=sys.stderr)
        return 1

    from core.twin_local_view import (
        data_root,
        list_queue,
        provider_status,
        read_home,
    )

    # --- HOME -----------------------------------------------------------
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


if __name__ == "__main__":
    sys.exit(main())
