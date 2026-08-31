from __future__ import annotations

from core.config import AppConfig, load_config

from app.health import health_snapshot


class ReleaseStatus:
    """Operational release readiness model for the platform."""

    def __init__(self, config: AppConfig):
        self.config = config

    def is_ready(self) -> bool:
        return (
            self.config.agent_count == 4
            and self.config.environment in {"development", "staging", "production"}
            and health_snapshot()["status"] == "healthy"
        )

    def manifest(self) -> dict:
        return {
            "platform_name": self.config.platform_name,
            "environment": self.config.environment,
            "version": self.config.version,
            "agent_count": self.config.agent_count,
            "status": "ready" if self.is_ready() else "not_ready",
        }


def release_manifest(environment: str = "production", version: str = "1.0.0-rc1") -> dict:
    """Return the release manifest for the active deployment candidate."""
    config = load_config({"environment": environment, "version": version})
    status = ReleaseStatus(config)
    return status.manifest()
