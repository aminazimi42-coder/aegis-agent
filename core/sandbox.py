from __future__ import annotations

from typing import Any, Dict

QUARANTINED = True


class SandboxValidationError(Exception):
    pass


class SandboxRunner:
    """Lightweight manifest sandbox validator.

    This is not an OS-level sandbox — it validates declared tools and
    rejects known-dangerous patterns. It is intended as a fast, deterministic
    pre-check before any runtime sandboxing is applied.
    """

    DENY_LIST = {"eval", "exec", "subprocess", "os.system"}
    ALLOWED_TOOLS = {"http", "db", "fs", "nlp"}

    @classmethod
    def validate_manifest(cls, manifest: Dict[str, Any]) -> None:
        if not isinstance(manifest, dict):
            raise SandboxValidationError("Manifest must be a mapping")

        tools = manifest.get("allowed_tools", [])
        for t in tools:
            if t not in cls.ALLOWED_TOOLS:
                raise SandboxValidationError(f"Disallowed tool: {t}")

        # quick scan of description and role for dangerous keywords
        combined = f"{manifest.get('description','')} {manifest.get('role','')}"
        for bad in cls.DENY_LIST:
            if bad in combined:
                raise SandboxValidationError(f"Manifest contains denied pattern: {bad}")
