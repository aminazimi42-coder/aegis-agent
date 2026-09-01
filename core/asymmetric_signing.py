from __future__ import annotations

import hashlib
import hmac
from typing import Optional

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


def verify_asymmetric(public_pem: bytes, payload: bytes, signature: bytes) -> bool:
    """Verify an asymmetric signature if cryptography is available.

    Falls back to HMAC-verify using the public_pem bytes as a shared secret
    when cryptography is not installed (deterministic fallback for tests).
    """
    if _HAS_CRYPTO:
        try:
            pub = load_pem_public_key(public_pem)
            if hasattr(pub, "verify"):
                # assume PKCS1v15-like verification where possible
                pub.verify(
                    signature,
                    payload,
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                return True
        except Exception:
            return False
    # fallback deterministic HMAC check using public_pem as key
    mac = hmac.new(public_pem, payload, hashlib.sha256).digest()
    return hmac.compare_digest(mac, signature)


def sign_asymmetric(private_key: Optional[bytes], payload: bytes) -> bytes:
    """Placeholder signer used in tests or when a private key is provided.

    If `cryptography` is not available or `private_key` is None, produce an HMAC
    using the provided private_key bytes (or b'default') as a deterministic fallback.
    """
    key = private_key or b"default"
    if _HAS_CRYPTO and private_key is not None:
        # In a real world setup we'd parse the private key and sign with it.
        # For now we fallback to HMAC to keep testability without extra deps.
        pass
    return hmac.new(key, payload, hashlib.sha256).digest()
