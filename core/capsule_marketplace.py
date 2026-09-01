from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, List

from .agent_registry import AGENT_REGISTRY
from .types import AgentSpec


@dataclass
class Capsule:
    manifest: Dict[str, Any]
    bundle: Dict[str, Any]
    signature: str
    signer: str


class CapsuleVerificationError(Exception):
    pass


class CapsuleMarketplace:
    """Lightweight capsule marketplace supporting HMAC-signed capsules.

    This implementation uses HMAC-SHA256 for signing and verifies that the
    manifest contains required fields and allowed tools only.
    """

    ALLOWED_TOOLS = {"http", "db", "fs", "nlp"}

    def __init__(self) -> None:
        self._installed: List[Capsule] = []

    @staticmethod
    def _canonical_payload(manifest: Dict[str, Any], bundle: Dict[str, Any]) -> bytes:
        payload = {"manifest": manifest, "bundle": bundle}
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _verify_hmac(payload: bytes, signature_hex: str, key: bytes) -> bool:
        mac = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, signature_hex)

    def verify_capsule(self, capsule: Dict[str, Any], trusted_keys: Dict[str, bytes]) -> None:
        if "manifest" not in capsule or "signature" not in capsule or "signer" not in capsule:
            raise CapsuleVerificationError("Malformed capsule: missing required fields")

        manifest = capsule["manifest"]
        bundle = capsule.get("bundle", {})
        signature = capsule["signature"]
        signer = capsule["signer"]

        if signer not in trusted_keys:
            raise CapsuleVerificationError("Unknown signer or untrusted key")

        payload = self._canonical_payload(manifest, bundle)
        key = trusted_keys[signer]
        if not self._verify_hmac(payload, signature, key):
            raise CapsuleVerificationError("Signature verification failed")

        # Basic manifest schema checks
        required = {"name", "role", "description", "capabilities", "allowed_tools"}
        if not required.issubset(set(manifest.keys())):
            raise CapsuleVerificationError("Manifest missing required fields")

        # Ensure allowed_tools are permitted
        for t in manifest.get("allowed_tools", []):
            if t not in self.ALLOWED_TOOLS:
                raise CapsuleVerificationError(f"Tool not allowed: {t}")

    def register_capsule(
        self, capsule: Dict[str, Any], trusted_keys: Dict[str, bytes]
    ) -> AgentSpec:
        self.verify_capsule(capsule, trusted_keys)
        manifest = capsule["manifest"]
        spec = AgentSpec(
            name=manifest["name"],
            role=manifest["role"],
            description=manifest["description"],
            capabilities=list(manifest.get("capabilities", [])),
        )
        # Append to global registry
        AGENT_REGISTRY.append(spec)
        installed_capsule = Capsule(
            manifest=manifest,
            bundle=capsule.get("bundle", {}),
            signature=capsule["signature"],
            signer=capsule["signer"],
        )
        self._installed.append(installed_capsule)
        return spec

    def installed_capsules(self) -> List[Capsule]:
        return list(self._installed)


# Simple singleton for convenience
CapsuleMarketplaceSingleton = CapsuleMarketplace()
