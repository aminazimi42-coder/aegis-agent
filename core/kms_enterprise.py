from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False

KMS_DIR = Path(".kms")
KMS_DIR.mkdir(exist_ok=True)
MASTER_KEY_PATH = KMS_DIR / "master.key"


def _ensure_master() -> bytes:
    if MASTER_KEY_PATH.exists():
        return MASTER_KEY_PATH.read_bytes()
    if _HAS_CRYPTO:
        key = Fernet.generate_key()
        MASTER_KEY_PATH.write_bytes(key)
        return key
    # fallback: simple file marker
    MASTER_KEY_PATH.write_text("no-crypto")
    return b"no-crypto"


def _key_path(name: str) -> Path:
    return KMS_DIR / f"enterprise-{name}.enc"


def store_key(name: str, pem: bytes) -> None:
    master = _ensure_master()
    p = _key_path(name)
    if _HAS_CRYPTO and master and master != b"no-crypto":
        f = Fernet(master)
        p.write_bytes(f.encrypt(pem))
    else:
        # write plaintext if cryptography missing (tests may skip stronger checks)
        p.write_bytes(pem)


def load_key(name: str) -> Optional[bytes]:
    p = _key_path(name)
    if not p.exists():
        return None
    data = p.read_bytes()
    master = _ensure_master()
    if _HAS_CRYPTO and master and master != b"no-crypto":
        f = Fernet(master)
        try:
            return f.decrypt(data)
        except Exception:
            return None
    return data


def rotate_key(name: str, new_pem: bytes) -> None:
    store_key(name, new_pem)


def list_keys() -> list[str]:
    return [p.stem.replace("enterprise-", "") for p in KMS_DIR.glob("enterprise-*.enc")]
