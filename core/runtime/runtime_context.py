from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from core.config import AppConfig


@dataclass(frozen=True)
class RuntimeContext:
    """Production-oriented runtime metadata for the platform."""

    app_name: str
    environment: str
    version: str
    agent_count: int
    debug: bool = False

    @classmethod
    def from_config(cls, config: AppConfig) -> "RuntimeContext":
        return cls(
            app_name=config.platform_name,
            environment=config.environment,
            version=config.version,
            agent_count=config.agent_count,
            debug=config.debug,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "version": self.version,
            "agent_count": self.agent_count,
            "debug": self.debug,
        }
