from __future__ import annotations

from enum import Enum


class HealthStatus(str, Enum):
    """Health state for the platform runtime."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


def health_snapshot() -> dict:
    """Return a basic operational snapshot for service health checks."""
    return {
        "service": "Aegis Agent Platform",
        "status": HealthStatus.HEALTHY.value,
        "agent_count": 4,
        "version": "0.6.0-a",
        "checks": {
            "config": "ok",
            "security": "ok",
            "agents": "ok",
        },
        "telemetry": {
            "status": "healthy",
            "security": "secure",
            "runtime": "stable",
        },
    }
