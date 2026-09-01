from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List

from core.evidence_ledger import EvidenceLedgerSingleton


@dataclass
class Role:
    name: str
    permissions: List[str] = field(default_factory=list)


class AuthorityMatrix:
    """Manage roles and permissions per-tenant and actor.

    - roles: global role definitions
    - assignments: mapping tenant_id -> actor -> list of role names
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._roles: Dict[str, Role] = {}
        self._assignments: Dict[str, Dict[str, List[str]]] = {}

    def define_role(self, role_name: str, permissions: List[str]) -> None:
        with self._lock:
            self._roles[role_name] = Role(name=role_name, permissions=list(permissions))
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="authority_matrix",
                action="define_role",
                payload={"role": role_name, "permissions": permissions},
            )

    def assign_role(self, tenant_id: str, actor: str, role_name: str) -> None:
        with self._lock:
            self._assignments.setdefault(tenant_id, {}).setdefault(actor, []).append(role_name)
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="authority_matrix",
                action="assign_role",
                payload={"actor": actor, "role": role_name},
            )

    def revoke_role(self, tenant_id: str, actor: str, role_name: str) -> bool:
        with self._lock:
            roles = self._assignments.get(tenant_id, {}).get(actor, [])
            if role_name in roles:
                roles.remove(role_name)
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor="authority_matrix",
                    action="revoke_role",
                    payload={"actor": actor, "role": role_name},
                )
                return True
            return False

    def check_permission(self, tenant_id: str, actor: str, permission: str) -> bool:
        with self._lock:
            roles = self._assignments.get(tenant_id, {}).get(actor, [])
            for r in roles:
                role = self._roles.get(r)
                if role and permission in role.permissions:
                    EvidenceLedgerSingleton.append_entry(
                        tenant_id=tenant_id,
                        actor="authority_matrix",
                        action="check_permission",
                        payload={"actor": actor, "permission": permission, "result": True},
                    )
                    return True
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="authority_matrix",
                action="check_permission",
                payload={"actor": actor, "permission": permission, "result": False},
            )
            return False


AuthorityMatrixSingleton = AuthorityMatrix()
