from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, List

from .agent_registry import AGENT_REGISTRY
from .asymmetric_signing import verify_asymmetric
from .durable_registry import remove_agent, save_agent
from .evidence_ledger import EvidenceLedgerSingleton
from .human_authority import HumanAuthority
from .reversible_workflow import ReversibleWorkflowManager
from .runtime_sandbox import RuntimeSandboxSingleton
from .sandbox import SandboxRunner
from .scorecard import ScorecardSingleton
from .types import AgentSpec

QUARANTINED = True


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
        self._auth = HumanAuthority()
        self._reversible = ReversibleWorkflowManager()

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
        sig_type = capsule.get("signature_type", "hmac")

        if signer not in trusted_keys:
            raise CapsuleVerificationError("Unknown signer or untrusted key")

        payload = self._canonical_payload(manifest, bundle)
        key = trusted_keys[signer]
        if sig_type == "asymmetric":
            # signature expected as bytes; tests may provide hex
            if isinstance(signature, (bytes, bytearray)):
                sig_bytes = signature
            else:
                sig_bytes = bytes.fromhex(signature)

            if not verify_asymmetric(key, payload, sig_bytes):
                raise CapsuleVerificationError(
                    "Asymmetric signature verification failed"
                )
        else:
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

        # Sandbox-level manifest validation
        try:
            SandboxRunner.validate_manifest(manifest)
        except Exception as exc:  # pragma: no cover - defensive
            raise CapsuleVerificationError(f"Sandbox validation failed: {exc}") from exc

    def register_capsule(
        self, capsule: Dict[str, Any], trusted_keys: Dict[str, bytes]
    ) -> AgentSpec:
        # Use reversible manager to make capsule install atomic
        self._reversible.begin()
        tenant_id = capsule.get("manifest", {}).get("tenant_id", "default")
        # verify signature/schema
        self.verify_capsule(capsule, trusted_keys)
        # record signature in scorecard
        sig_type = capsule.get("signature_type", "hmac")
        ScorecardSingleton.record_signature(tenant_id, asymmetric=(sig_type == "asymmetric"))
        manifest = capsule["manifest"]

        # run authority check for install
        action_text = f"install {manifest.get('name')}: {manifest.get('description', '')}"
        try:
            self._auth.check_authorization(
                action_text, {"tenant_sensitive": manifest.get("tenant_sensitive", False)}
            )
        except Exception:
            self._reversible.rollback()
            raise

        spec = AgentSpec(
            name=manifest["name"],
            role=manifest.get("role", "capsule"),
            description=manifest.get("description", ""),
            capabilities=list(manifest.get("capabilities", [])),
        )

        # Optional sandbox probe: perform a dry-run execution in the runtime sandbox
        if manifest.get("sandbox_probe"):
            try:
                RuntimeSandboxSingleton.execute(manifest, {})
                ScorecardSingleton.record_sandbox(manifest.get("tenant_id", "default"), passed=True)
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=manifest.get("tenant_id", "default"),
                    actor=capsule.get("signer", "unknown"),
                    action="sandbox_probe",
                    payload={"name": manifest.get("name")},
                )
            except Exception:
                # treat probe failures as verification failure
                self._reversible.rollback()
                raise CapsuleVerificationError("Sandbox probe failed") from None

        def do_register():
            AGENT_REGISTRY.append(spec)
            save_agent(spec)
            # ledger evidence for successful install
            try:
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor=capsule.get("signer", "unknown"),
                    action="install_capsule",
                    payload={"name": spec.name, "role": spec.role},
                )
            except Exception:
                # ledger is best-effort; do not fail install solely due to ledger
                pass

        def undo_register():
            # remove from memory registry and durable registry
            for i in range(len(AGENT_REGISTRY) - 1, -1, -1):
                if AGENT_REGISTRY[i].name == spec.name:
                    AGENT_REGISTRY.pop(i)
                    break
            remove_agent(spec.name)
            # remove last ledger entry as part of rollback
            try:
                EvidenceLedgerSingleton.remove_last(1)
            except Exception:
                pass

        try:
            self._reversible.execute(do_register, undo_register)
        except Exception:
            self._reversible.rollback()
            raise

        # commit install
        try:
            self._reversible.commit()
        except Exception:
            self._reversible.rollback()
            raise

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
