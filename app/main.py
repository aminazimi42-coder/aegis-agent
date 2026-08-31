"""Aegis Agent Platform startup entry point.

Created by Azimi Innovation Lab.
Owned by AI Architect Amin Azimi.
Developed through the End-to-End System Development model.
"""

from __future__ import annotations

from core.config import load_config
from core.runtime.runtime_context import RuntimeContext

from app.api.health import platform_status
from app.server import create_app
from app.services.runtime_service import RuntimeService

app = create_app()


def main() -> None:
    """Production startup entry point for the platform."""
    config = load_config()
    context = RuntimeContext.from_config(config)
    runtime_service = RuntimeService(context)
    startup = runtime_service.bootstrap()
    status = platform_status()

    print({
        "startup": startup,
        "status": status,
    })


if __name__ == "__main__":
    main()
