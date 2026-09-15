"""Public-demo mode detector (T186).

A single helper that returns True when the process is running as the
public Render demo, False on a local operator laptop.  The demo is
detected from the ``AEGIS_PUBLIC_DEMO`` env flag (``1`` or ``true``) or
the presence of the ``RENDER`` env var; it is **not** detected from the
hostname string alone inside execute.
"""

from __future__ import annotations

import os

_TRUE_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def is_public_demo() -> bool:
    """Return True when running as the public Render demo.

    - ``AEGIS_PUBLIC_DEMO`` set to ``1``/``true`` → demo.
    - ``RENDER`` env var present (any non-empty value) → demo.
    - Both unset (local laptop) → ``False``.
    """
    demo_flag = os.environ.get("AEGIS_PUBLIC_DEMO", "").strip().lower()
    if demo_flag in _TRUE_STRINGS:
        return True
    render_flag = os.environ.get("RENDER", "").strip()
    if render_flag:
        return True
    return False
