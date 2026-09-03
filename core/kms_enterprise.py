from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


def _kms_dir() -> Path:
    base = os.environ.get("AEGIS_DATA_DIR")
    if base:
        return Path(base) / ".kms"
    return Path(".kms")


# Module-level constants kept for backward compatibility, but all path
# resolution goes through _kms_dir() so AEGIS_DATA_DIR is respected at call time.
KMS_DIR = _kms_dir()


def _master_key_path() -> Path:
    return _kms_dir() / "master.key"


def _ensure_master() -> bytes:
    mk = _master_key_path()
    if mk.exists():
        return mk.read_bytes()
    _kms_dir().mkdir(parents=True, exist_ok=True)
    if _HAS_CRYPTO:
        key = Fernet.generate_key()
        mk.write_bytes(key)
        return key
    # fallback: simple file marker
    mk.write_text("no-crypto")
    return b"no-crypto"


def _key_path(name: str) -> Path:
    return _kms_dir() / f"enterprise-{name}.enc"


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
    return [
        p.stem.replace("enterprise-", "")
        for p in _kms_dir().glob("enterprise-*.enc")
    ]


def validate_rotation(name: str, max_age_days: int = 90) -> bool:
    """Validate that a stored key was rotated recently enough.

    This is a pragmatic check used by CI/helm hooks to detect stale keys.
    Returns False if the key or master key is missing.
    """
    import datetime

    p = _key_path(name)
    mk = _master_key_path()
    if not p.exists() or not mk.exists():
        return False
    mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
    age_days = (datetime.datetime.now() - mtime).days
    return age_days <= int(max_age_days)
