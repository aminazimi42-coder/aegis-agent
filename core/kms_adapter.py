from __future__ import annotations

from pathlib import Path
from typing import Optional

KMS_DIR = Path(".kms")
KMS_DIR.mkdir(exist_ok=True)


def _key_path(name: str) -> Path:
    return KMS_DIR / f"{name}.pem"


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
    return [p.stem for p in KMS_DIR.glob("*.pem")]
