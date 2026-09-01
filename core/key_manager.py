from __future__ import annotations

from .asymmetric_signing import sign_asymmetric, verify_asymmetric


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

    def verify(self, key_name: str, payload: bytes, signature: bytes) -> bool:
        pub = self._pubkeys.get(key_name)
        if pub is None:
            return False
        return verify_asymmetric(pub, payload, signature)

    def sign(self, key_name: str, payload: bytes) -> bytes:
        priv = self._privkeys.get(key_name)
        return sign_asymmetric(priv, payload)


KeyManagerSingleton = KeyManager()
