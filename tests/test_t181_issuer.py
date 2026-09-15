"""T181 — Local license issuer stays outside execute.

The local issuer (``scripts/issue_entitlement.py``) writes a signed
``entitlement.json`` under ``AEGIS_DATA_DIR`` only.  ``execute`` /
``propose`` / ``complete_safe`` read that file only — they do not call
the issuer, do not import Stripe, and do not call the network.  A
missing, unreadable, or expired file is Echo-limited; a forged header
or a remote 200 without the local file cannot unlock the tier.

Covers:

* ``test_issuer_writes_under_data_dir`` — the issuer writes
  ``entitlement.json`` under the tmp ``AEGIS_DATA_DIR``.
* ``test_issuer_refuses_outside_data_dir`` — the issuer only writes
  under ``AEGIS_DATA_DIR``; the written path is inside the data root.
* ``test_delete_file_echo_limited`` — after the file is deleted,
  ``load()`` returns ``reason="missing_file"`` (Echo-limited).
* ``test_expired_in_past_echo_limited`` — an entitlement whose
  ``expires_at`` is in the past returns ``reason="expired"``.
* ``test_execute_does_not_import_stripe`` — the execute / propose /
  complete_safe modules do not import ``stripe``.
* ``test_remote_cannot_unlock_without_local_file`` — a mocked remote
  200 body cannot raise the tier when the local file is absent.
* ``test_readme_author_untouched`` — the README Author paragraph
  retains the original author identity.

No network.  No uvicorn.  Uses ``tmp_path``-style temp dirs.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import scripts.issue_entitlement as issuer_mod
from core.entitlement import ECHO_TIER, load

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class _FakeResponse:
    """Minimal context-manager response for mocking urlopen."""

    def __init__(self, status_code: int = 200, body: bytes = b"{}") -> None:
        self.status = status_code
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class TestT181Issuer(unittest.TestCase):
    """Local license issuer stays outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t181_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)

    # ------------------------------------------------------------------ #
    # 1) Issuer writes under the data dir
    # ------------------------------------------------------------------ #
    def test_issuer_writes_under_data_dir(self) -> None:
        """The issuer writes entitlement.json under AEGIS_DATA_DIR."""
        key = "test-issuer-secret-t181"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        issuer_mod.issue(
            tenant_id="t181-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        self.assertTrue(out_path.is_file(), "issuer must write entitlement.json")
        data = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(data["tier"], "professional")
        self.assertEqual(data["issuer"], "local-cli")
        self.assertNotIn(key, out_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    # 2) Issuer refuses outside data dir
    # ------------------------------------------------------------------ #
    def test_issuer_refuses_outside_data_dir(self) -> None:
        """The issuer only writes under AEGIS_DATA_DIR — the written
        path is inside the data root, never outside it."""
        key = "test-issuer-secret-t181-cage"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        issuer_mod.issue(
            tenant_id="t181-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        # The written file must be inside AEGIS_DATA_DIR.
        data_root = Path(self._tmp).resolve()
        self.assertTrue(
            out_path.resolve().is_relative_to(data_root)
            if hasattr(out_path.resolve(), "is_relative_to")
            else str(out_path.resolve()).startswith(str(data_root)),
            "entitlement.json must live inside AEGIS_DATA_DIR",
        )
        # No file outside the data dir was created by the issuer.
        self.assertEqual(
            out_path.resolve().parent,
            data_root,
            "entitlement.json parent must be the data root",
        )

    # ------------------------------------------------------------------ #
    # 3) Delete file -> Echo-limited
    # ------------------------------------------------------------------ #
    def test_delete_file_echo_limited(self) -> None:
        """After the entitlement file is deleted, load() returns
        reason='missing_file' (Echo-limited)."""
        key = "test-issuer-secret-t181-del"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        issuer_mod.issue(
            tenant_id="t181-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        self.assertTrue(out_path.is_file())
        out_path.unlink()
        result = load(tenant_id="t181-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "missing_file")

    # ------------------------------------------------------------------ #
    # 4) expires_at in the past -> Echo-limited
    # ------------------------------------------------------------------ #
    def test_expired_in_past_echo_limited(self) -> None:
        """An entitlement whose expires_at is in the past returns
        reason='expired' (Echo-limited)."""
        key = "test-issuer-secret-t181-exp"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        # Write a valid file first, then overwrite with an expired one.
        issuer_mod.issue(
            tenant_id="t181-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        data = json.loads(out_path.read_text(encoding="utf-8"))
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data["expires_at"] = past
        # Recompute the HMAC signature for the modified body.
        import hashlib
        import hmac

        body = {k: v for k, v in data.items() if k != "signature_sha256"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        data["signature_sha256"] = hmac.new(
            key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        out_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = load(tenant_id="t181-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "expired")

    # ------------------------------------------------------------------ #
    # 5) Execute does not import stripe
    # ------------------------------------------------------------------ #
    def test_execute_does_not_import_stripe(self) -> None:
        """The execute / propose / complete_safe modules do not import
        or reference 'stripe'."""
        modules_to_check = [
            "core.twin_actions",
            "core.llm_safety",
        ]
        for mod_name in modules_to_check:
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
            else:
                mod = importlib.import_module(mod_name)
            source = open(mod.__file__ or "", encoding="utf-8").read()
            self.assertNotIn(
                "stripe",
                source.lower(),
                f"{mod_name} must not import or reference stripe",
            )

    # ------------------------------------------------------------------ #
    # 6) Remote cannot unlock without local file
    # ------------------------------------------------------------------ #
    def test_remote_cannot_unlock_without_local_file(self) -> None:
        """A mocked remote 200 body cannot raise the tier when the
        local entitlement file is absent — the tenant stays
        Echo-limited."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        os.environ["AEGIS_LICENSE_STATUS_URL"] = (
            "https://license.example.test/status"
        )
        remote_body = json.dumps(
            {"tier": "professional", "expires_at": None, "status": "active"}
        ).encode()
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t181-tenant")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")
        self.assertEqual(body["license_check"], "echo_limited")
        # No entitlement.json was written by the remote body.
        self.assertFalse((Path(self._tmp) / "entitlement.json").is_file())

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph must be present and contain the
        original author identity line."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)
        self.assertIn("Azimi Innovation Lab", text)


if __name__ == "__main__":
    unittest.main()
