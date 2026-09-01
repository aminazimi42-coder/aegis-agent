from __future__ import annotations

from typing import Dict, List

from core.authority_matrix import AuthorityMatrixSingleton
from core.data_governance import ConsentStoreSingleton, PolicyEngineSingleton
from core.evidence_ledger import EvidenceLedgerSingleton


class AuthorizationError(Exception):
    pass


def authorize_action(
    tenant_id: str, actor: str, action: str, required_scope: List[str]
) -> Dict[str, object]:
    """Authorize an action by checking policy, consent, and authority.

    Returns a dict with `allowed` and `reason` keys. Raises AuthorizationError on
    hard deny.
    """
    # Policy check: data labels allowed?
    for s in required_scope:
        if not PolicyEngineSingleton.allowed(s):
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="secure_governance",
                action="authorize",
                payload={
                    "actor": actor,
                    "action": action,
                    "scope": required_scope,
                    "result": False,
                    "reason": "policy_denied",
                },
            )
            raise AuthorizationError("policy_denied")

    # Consent check
    if not ConsentStoreSingleton.check(tenant_id, actor, required_scope):
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor="secure_governance",
            action="authorize",
            payload={
                "actor": actor,
                "action": action,
                "scope": required_scope,
                "result": False,
                "reason": "consent_missing",
            },
        )
        raise AuthorizationError("consent_missing")

    # Authority check
    if not AuthorityMatrixSingleton.check_permission(tenant_id, actor, action):
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor="secure_governance",
            action="authorize",
            payload={
                "actor": actor,
                "action": action,
                "scope": required_scope,
                "result": False,
                "reason": "not_authorized",
            },
        )
        raise AuthorizationError("not_authorized")

    EvidenceLedgerSingleton.append_entry(
        tenant_id=tenant_id,
        actor="secure_governance",
        action="authorize",
        payload={"actor": actor, "action": action, "scope": required_scope, "result": True},
    )
    return {"allowed": True, "reason": "ok"}
