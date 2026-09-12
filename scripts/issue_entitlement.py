#!/usr/bin/env python3
"""Local signed entitlement issuer CLI (T154).

Writes a signed ``entitlement.json`` under ``AEGIS_DATA_DIR`` (default
``$HOME/.aegis``).  The signature is an HMAC-SHA256 hex digest of the
canonical JSON payload, keyed with a local issuer secret.

The issuer secret is read from ``--key-file`` (a path to a text file
containing the secret) or, when that is omitted, from the
``AEGIS_ENTITLEMENT_ISSUER_KEY`` environment variable.  When neither is
present the CLI refuses to run and writes nothing.

The secret is never printed and never written into the output file.
No network calls are made.  No payment library is imported.

Usage::

    python scripts/issue_entitlement.py \
        --tenant my-tenant \
        --tier professional \
        --days 30 \
        --key-file /path/to/issuer.key

    AEGIS_ENTITLEMENT_ISSUER_KEY=secret python scripts/issue_entitlement.py \
        --tenant my-tenant --tier professional
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ISSUER: str = "local-cli"
_ENV_KEY: str = "AEGIS_ENTITLEMENT_ISSUER_KEY"
_VALID_TIERS: tuple[str, ...] = ("echo", "professional")


def _data_root() -> Path:
    """Return the on-disk data root (``AEGIS_DATA_DIR`` or ``~/.aegis``)."""
    env_val = os.getenv("AEGIS_DATA_DIR", "")
    if env_val and env_val.strip():
        root = Path(env_val)
    else:
        root = Path.home() / ".aegis"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_key(args: argparse.Namespace) -> str | None:
    """Return the issuer secret from ``--key-file`` or the environment.

    Returns ``None`` when neither source provides a key.
    """
    if args.key_file:
        p = Path(args.key_file)
        if not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8")
        return raw.strip()
    return os.getenv(_ENV_KEY, "").strip() or None


def _canonical_payload(payload: dict[str, Any]) -> str:
    """Return the canonical JSON of *payload* (no ``signature_sha256``)."""
    body = {k: v for k, v in payload.items() if k != "signature_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _sign(payload: dict[str, Any], key: str) -> str:
    """Return the HMAC-SHA256 hex digest of the canonical payload."""
    body = _canonical_payload(payload)
    return hmac.new(
        key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _build_payload(
    tenant_id: str, tier: str, days: int
) -> dict[str, Any]:
    """Build the canonical entitlement payload (pre-signature)."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)
    return {
        "tenant_id": tenant_id,
        "tier": tier,
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "issuer": _ISSUER,
    }


def issue(
    tenant_id: str, tier: str, days: int, key: str
) -> dict[str, Any]:
    """Build and sign an entitlement payload and write it to disk.

    Returns the signed payload dict.  Does not include the key in the
    output.
    """
    payload = _build_payload(tenant_id, tier, days)
    payload["signature_sha256"] = _sign(payload, key)
    out_path = _data_root() / "entitlement.json"
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a signed local entitlement.json under AEGIS_DATA_DIR.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant ID to bind this entitlement to.",
    )
    parser.add_argument(
        "--tier",
        choices=_VALID_TIERS,
        default="echo",
        help="Entitlement tier (default: echo).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days until expiry (default: 30).",
    )
    parser.add_argument(
        "--key-file",
        default=None,
        help="Path to a file containing the issuer secret.",
    )
    args = parser.parse_args(argv)

    key = _load_key(args)
    if not key:
        print(
            "error: no issuer key provided — pass --key-file or set "
            f"{_ENV_KEY}",
            file=sys.stderr,
        )
        return 1

    payload = issue(args.tenant, args.tier, args.days, key)
    out_path = _data_root() / "entitlement.json"
    print(f"signed entitlement written: {out_path}")
    print(f"tenant: {payload['tenant_id']}")
    print(f"tier: {payload['tier']}")
    print(f"expires_at: {payload['expires_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
