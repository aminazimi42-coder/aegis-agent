from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AppConfig:
    """Central configuration object for the platform."""

    platform_name: str = "Aegis Agent Platform"
    environment: str = "development"
    agent_count: int = 6
    debug: bool = False
    log_level: str = "INFO"
    version: str = "1.0.0-rc1"


def load_config(overrides: Optional[Dict[str, Any]] = None) -> AppConfig:
    """Load configuration from a dictionary and environment variables."""
    values = {
        "platform_name": os.getenv("AEGIS_PLATFORM_NAME", "Aegis Agent Platform"),
        "environment": os.getenv("AEGIS_ENVIRONMENT", "development"),
        "agent_count": int(os.getenv("AEGIS_AGENT_COUNT", "6")),
        "debug": os.getenv("AEGIS_DEBUG", "false").lower() == "true",
        "log_level": os.getenv("AEGIS_LOG_LEVEL", "INFO"),
        "version": os.getenv("AEGIS_VERSION", "1.0.0-rc1"),
    }

    if overrides:
        values.update({key: value for key, value in overrides.items() if value is not None})

    environment = values["environment"]
    if environment not in {"development", "staging", "production"}:
        environment = "development"

    return AppConfig(
        platform_name=values["platform_name"],
        environment=environment,
        agent_count=int(values["agent_count"]),
        debug=bool(values["debug"]),
        log_level=str(values["log_level"]).upper(),
        version=str(values["version"]),
    )
