from __future__ import annotations

from typing import Any, Dict

QUARANTINED = True


class RuntimeSandboxError(Exception):
    pass


class RuntimeSandbox:
    """Runtime sandbox runner stub.

    This is a lightweight placeholder to represent the runtime isolation
    component. It validates inputs and returns a deterministic response.
    Replace with container/process sandboxing for production.
    """

    def execute(self, manifest: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        # Basic safety check
        if not isinstance(manifest, dict) or "allowed_tools" not in manifest:
            raise RuntimeSandboxError("Invalid manifest")
        # Simulate isolated execution
        return {"status": "executed", "payload": payload, "manifest_name": manifest.get("name")}


RuntimeSandboxSingleton = RuntimeSandbox()
