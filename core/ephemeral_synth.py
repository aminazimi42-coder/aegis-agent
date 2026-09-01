from __future__ import annotations

from typing import Any, Dict

from .agent_registry import AGENT_REGISTRY
from .capsule_marketplace import CapsuleMarketplace, CapsuleVerificationError
from .evidence_ledger import EvidenceLedgerSingleton
from .human_authority import HumanAuthority
from .reversible_workflow import ReversibleWorkflowManager
from .sandbox import SandboxRunner, SandboxValidationError
from .scorecard import ScorecardSingleton
from .tenant_memory import TenantMemory
from .types import AgentSpec


class EphemeralSynthError(Exception):
    pass


class EphemeralSynthEngine:
    """Dynamically instantiate ephemeral agent templates and ensure teardown.

    The engine integrates with the `CapsuleMarketplace` for capsule verification,
    `HumanAuthority` for risk-weighted approvals, and `ReversibleWorkflowManager`
    to ensure atomic rollback of side-effects.
    """

    def __init__(self, marketplace: CapsuleMarketplace | None = None) -> None:
        self.marketplace = marketplace or CapsuleMarketplace()
        self.authority = HumanAuthority()
        self.reversible = ReversibleWorkflowManager()

    def synthesize_from_capsule(
        self, capsule: Dict[str, Any], trusted_keys: Dict[str, bytes]
    ) -> AgentSpec:
        """Verify capsule, perform authority check, instantiate agent, and register rollback."""
        # begin reversible context
        self.reversible.begin()

        # Verify capsule first (may raise CapsuleVerificationError)
        try:
            self.marketplace.verify_capsule(capsule, trusted_keys)
        except CapsuleVerificationError:
            self.reversible.rollback()
            raise

        manifest = capsule["manifest"]
        name = manifest["name"]

        # Risk assessment: treat install action as sensitive based on manifest
        action_text = f"install {name}: {manifest.get('description', '')}"
        try:
            _profile = self.authority.check_authorization(
                action_text, {"tenant_sensitive": manifest.get("tenant_sensitive", False)}
            )
        except Exception:
            # authority denied
            self.reversible.rollback()
            raise

        # Validate sandbox constraints before instantiation
        try:
            SandboxRunner.validate_manifest(manifest)
        except SandboxValidationError as exc:
            self.reversible.rollback()
            raise EphemeralSynthError("Manifest failed sandbox validation") from exc

        tenant_id = manifest.get("tenant_id", "default")
        # record sandbox pass
        ScorecardSingleton.record_sandbox(tenant_id, passed=True)

        # Instantiate agent spec and register into global registry
        spec = AgentSpec(
            name=manifest["name"],
            role=manifest.get("role", "ephemeral"),
            description=manifest.get("description", "ephemeral agent"),
            capabilities=list(manifest.get("capabilities", [])),
        )

        def do_register():
            AGENT_REGISTRY.append(spec)
            try:
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor=capsule.get("signer", "unknown"),
                    action="synthesize_ephemeral",
                    payload={"name": spec.name, "role": spec.role},
                )
            except Exception:
                pass

        def undo_register():
            # remove first matching by name
            for i in range(len(AGENT_REGISTRY) - 1, -1, -1):
                if AGENT_REGISTRY[i].name == spec.name:
                    AGENT_REGISTRY.pop(i)
                    break

            # remove last ledger entry as part of rollback
            try:
                EvidenceLedgerSingleton.remove_last(1)
            except Exception:
                pass

        # perform registration and register rollback
        try:
            self.reversible.execute(do_register, undo_register)
        except Exception:
            self.reversible.rollback()
            raise EphemeralSynthError("Failed to register ephemeral agent") from None

        # If everything is good, commit and return the spec
        try:
            self.reversible.commit()
        except Exception:
            # if commit fails, try rollback
            self.reversible.rollback()
            raise

        # Optionally prepare a RAG storage path for tenant-scoped persistence
        tenant_id = manifest.get("tenant_id")
        if manifest.get("persist_rag") and tenant_id:
            tm = TenantMemory()
            try:
                rag_path = tm.rag_storage_path(
                    tenant_id, namespace=manifest.get("rag_namespace", "default")
                )
                # record the path in tenant memory for discovery
                tm.store(
                    tenant_id=tenant_id,
                    key=f"rag:{name}",
                    value={"path": rag_path},
                    namespace=manifest.get("rag_namespace", "default"),
                )
            except Exception:
                # best-effort; do not fail the whole flow if path creation fails
                pass

        return spec

    def teardown(self, agent_name: str) -> bool:
        """Remove an ephemeral agent by name.

        Returns True if removed, False if not found.
        """
        for i in range(len(AGENT_REGISTRY) - 1, -1, -1):
            if AGENT_REGISTRY[i].name == agent_name:
                AGENT_REGISTRY.pop(i)
                return True
        return False
