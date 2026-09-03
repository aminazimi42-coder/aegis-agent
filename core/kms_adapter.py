from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _kms_dir() -> Path:
    base = os.environ.get("AEGIS_DATA_DIR")
    if base:
        return Path(base) / ".kms"
    return Path(".kms")


# Keep a module-level constant for backward compatibility but compute
# paths dynamically so AEGIS_DATA_DIR is respected at call time.
KMS_DIR = _kms_dir()


def _ensure_dir() -> Path:
    d = _kms_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key_path(name: str) -> Path:
    return _ensure_dir() / f"{name}.pem"


def store_key(name: str, pem: bytes) -> None:
    p = _key_path(name)
    p.write_bytes(pem)


def load_key(name: str) -> Optional[bytes]:
    p = _key_path(name)
    if not p.exists():
        return None
    return p.read_bytes()


def rotate_key(name: str, new_pem: bytes) -> None:
    store_key(name, new_pem)


def list_keys() -> list[str]:
    return [p.stem for p in _ensure_dir().glob("*.pem")]
