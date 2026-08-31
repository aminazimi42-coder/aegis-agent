from __future__ import annotations

from app.health import health_snapshot
from core.config import load_config
from core.diagnostics.health import RuntimeDiagnostics
from core.monitoring.metrics import PlatformMetrics
from core.runtime.runtime_context import RuntimeContext


def liveness_check() -> dict:
    """Returns the service liveness state."""
    snapshot = health_snapshot()
    return {
        "service": snapshot["service"],
        "status": snapshot["status"],
        "kind": "liveness",
    }


def readiness_check() -> dict:
    """Returns the platform readiness signal for runtime environments."""
    config = load_config()
    context = RuntimeContext.from_config(config)
    diagnostics = RuntimeDiagnostics(context)
    return diagnostics.report()


def platform_status() -> dict:
    """Aggregates liveness, readiness, and telemetry in a single payload."""
    metrics = PlatformMetrics().snapshot()
    return {
        "liveness": liveness_check(),
        "readiness": readiness_check(),
        "health": health_snapshot(),
        "telemetry": metrics["telemetry"],
    }
