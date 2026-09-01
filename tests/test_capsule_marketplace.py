import hashlib
import hmac
import json
import unittest

from core.agent_registry import AGENT_REGISTRY
from core.capsule_marketplace import CapsuleMarketplace, CapsuleVerificationError


def sign_capsule(manifest: dict, bundle: dict, key: bytes) -> str:
    payload = json.dumps(
        {"manifest": manifest, "bundle": bundle}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


class CapsuleMarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.market = CapsuleMarketplace()
        self.trusted = {"vendor1": b"secret-key-1"}
        self._orig_registry_len = len(AGENT_REGISTRY)

    def tearDown(self):
        # restore agent registry to original state to avoid test pollution
        while len(AGENT_REGISTRY) > self._orig_registry_len:
            AGENT_REGISTRY.pop()

    def test_valid_capsule_registers(self):
        manifest = {
            "name": "CapsuleAgent",
            "role": "Test role",
            "description": "A test capsule",
            "capabilities": ["testing"],
            "allowed_tools": ["http"],
        }
        bundle = {"prompts": []}
        signature = sign_capsule(manifest, bundle, self.trusted["vendor1"])
        capsule = {
            "manifest": manifest,
            "bundle": bundle,
            "signature": signature,
            "signer": "vendor1",
        }

        spec = self.market.register_capsule(capsule, self.trusted)
        self.assertEqual(spec.name, "CapsuleAgent")

    def test_tampered_capsule_fails(self):
        manifest = {
            "name": "CapsuleAgent",
            "role": "Test role",
            "description": "A test capsule",
            "capabilities": ["testing"],
            "allowed_tools": ["http"],
        }
        bundle = {"prompts": []}
        signature = sign_capsule(manifest, bundle, self.trusted["vendor1"])
        # tamper manifest after signing
        tampered = dict(manifest)
        tampered["name"] = "TamperedAgent"
        capsule = {
            "manifest": tampered,
            "bundle": bundle,
            "signature": signature,
            "signer": "vendor1",
        }

        with self.assertRaises(CapsuleVerificationError):
            self.market.register_capsule(capsule, self.trusted)

    def test_unauthorized_signer_fails(self):
        manifest = {
            "name": "CapsuleAgent",
            "role": "Test role",
            "description": "A test capsule",
            "capabilities": ["testing"],
            "allowed_tools": ["http"],
        }
        bundle = {"prompts": []}
        # sign with unknown key
        payload = json.dumps(
            {"manifest": manifest, "bundle": bundle}, sort_keys=True, separators=(",", ":")
        )
        signature = hmac.new(b"bad-key", payload.encode("utf-8"), hashlib.sha256).hexdigest()
        capsule = {
            "manifest": manifest,
            "bundle": bundle,
            "signature": signature,
            "signer": "unknown",
        }

        with self.assertRaises(CapsuleVerificationError):
            self.market.register_capsule(capsule, self.trusted)


if __name__ == "__main__":
    unittest.main()
