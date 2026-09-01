import hashlib
import hmac
import json
import unittest

from core.agent_registry import AGENT_REGISTRY
from core.capsule_marketplace import CapsuleVerificationError
from core.ephemeral_synth import EphemeralSynthEngine


def sign_capsule(manifest: dict, bundle: dict, key: bytes) -> str:
    payload = json.dumps(
        {"manifest": manifest, "bundle": bundle}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


class EphemeralSynthTests(unittest.TestCase):
    def setUp(self):
        self.engine = EphemeralSynthEngine()
        self.trusted = {"vendor1": b"secret-key-1"}
        self.orig_len = len(AGENT_REGISTRY)

    def tearDown(self):
        # restore registry
        while len(AGENT_REGISTRY) > self.orig_len:
            AGENT_REGISTRY.pop()

    def test_synthesize_and_teardown(self):
        manifest = {
            "name": "EphemeralX",
            "role": "ephemeral",
            "description": "temp agent",
            "capabilities": ["test"],
            "allowed_tools": ["http"],
        }
        bundle = {}
        signature = sign_capsule(manifest, bundle, self.trusted["vendor1"])
        capsule = {
            "manifest": manifest,
            "bundle": bundle,
            "signature": signature,
            "signer": "vendor1",
        }

        spec = self.engine.synthesize_from_capsule(capsule, self.trusted)
        self.assertEqual(spec.name, "EphemeralX")
        self.assertTrue(any(a.name == "EphemeralX" for a in AGENT_REGISTRY))

        removed = self.engine.teardown("EphemeralX")
        self.assertTrue(removed)
        self.assertFalse(any(a.name == "EphemeralX" for a in AGENT_REGISTRY))

    def test_tampered_capsule_rejected(self):
        manifest = {
            "name": "EphemeralX",
            "role": "ephemeral",
            "description": "temp agent",
            "capabilities": ["test"],
            "allowed_tools": ["http"],
        }
        bundle = {}
        signature = sign_capsule(manifest, bundle, self.trusted["vendor1"])
        tampered = dict(manifest)
        tampered["name"] = "Tampered"
        capsule = {
            "manifest": tampered,
            "bundle": bundle,
            "signature": signature,
            "signer": "vendor1",
        }

        with self.assertRaises(CapsuleVerificationError):
            self.engine.synthesize_from_capsule(capsule, self.trusted)

    def test_authority_denies_high_risk(self):
        manifest = {
            "name": "DangerAgent",
            "role": "ephemeral",
            "description": "transfer funds and exfiltrate " * 50,
            "capabilities": ["transfer"],
            "allowed_tools": ["http"],
            "tenant_sensitive": True,
        }
        bundle = {}
        signature = sign_capsule(manifest, bundle, self.trusted["vendor1"])
        capsule = {
            "manifest": manifest,
            "bundle": bundle,
            "signature": signature,
            "signer": "vendor1",
        }

        with self.assertRaises(PermissionError):
            self.engine.synthesize_from_capsule(capsule, self.trusted)


if __name__ == "__main__":
    unittest.main()
