from __future__ import annotations

from . import asymmetric_signing
from .asymmetric_signing import sign_asymmetric, verify_asymmetric
from .evidence_ledger import EvidenceLedgerSingleton
from .kms_adapter import rotate_key as kms_rotate_key
from .kms_adapter import store_key
from .scorecard import ScorecardSingleton


class KeyManager:
    """Pluggable key manager abstraction.

    For Phase16 we provide a minimal wrapper around existing asymmetric signing
    helpers. In production this should integrate with a KMS or secure store.
    """

    def __init__(self) -> None:
        # simple in-memory PEM store for tests and local usage
        self._pubkeys: dict[str, bytes] = {}
        self._privkeys: dict[str, bytes] = {}

    def register_public_key(self, name: str, pem: bytes) -> None:
        self._pubkeys[name] = pem

    def register_private_key(self, name: str, pem: bytes) -> None:
        self._privkeys[name] = pem
        # persist to KMS for durability
        try:
            store_key(name, pem)
        except Exception:
            pass

    def verify(self, key_name: str, payload: bytes, signature: bytes) -> bool:
        pub = self._pubkeys.get(key_name)
        if pub is None:
            return False
        return verify_asymmetric(pub, payload, signature)

    def sign(self, key_name: str, payload: bytes) -> bytes:
        priv = self._privkeys.get(key_name)
        return sign_asymmetric(priv, payload)

    def rotate_key(
        self,
        name: str,
        new_private_pem: bytes,
        new_public_pem: bytes | None = None,
    ) -> None:
        """Rotate a private key for `name`. Optionally update public key too."""
        self._privkeys[name] = new_private_pem
        if new_public_pem is not None:
            self._pubkeys[name] = new_public_pem
        # persist rotation to KMS
        try:
            kms_rotate_key(name, new_private_pem)
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="key_manager",
                action="rotate_key",
                payload={"name": name},
            )
            # record a signature event if asymmetric is available
            ScorecardSingleton.record_signature(
                name,
                asymmetric=bool(new_public_pem and asymmetric_signing._HAS_CRYPTO),
            )
        except Exception:
            pass

    def export_public(self, name: str) -> bytes | None:
        return self._pubkeys.get(name)

    def list_keys(self) -> list[str]:
        return sorted(set(list(self._pubkeys.keys()) + list(self._privkeys.keys())))

    def remove_key(self, name: str) -> None:
        self._pubkeys.pop(name, None)
        self._privkeys.pop(name, None)


KeyManagerSingleton = KeyManager()
