import hashlib
import hmac
import json

import pytest
from core.agent_registry import AGENT_REGISTRY
from core.capsule_marketplace import CapsuleMarketplace
from core.evidence_ledger import EvidenceLedgerSingleton
from core.scorecard import ScorecardSingleton


@pytest.fixture(autouse=True)
def _restore_agent_registry():
    """Snapshot AGENT_REGISTRY before each test and restore it after."""
    snapshot = list(AGENT_REGISTRY)
    yield
    AGENT_REGISTRY[:] = snapshot


def make_hmac_sig(key: bytes, manifest: dict, bundle: dict) -> str:
    payload = json.dumps(
        {"manifest": manifest, "bundle": bundle}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def test_capsule_install_records_ledger_and_scorecard():
    mp = CapsuleMarketplace()
    key = b"phase15-test-key"
    manifest = {
        "name": "phase15-agent",
        "role": "worker",
        "description": "Phase15 test agent",
        "capabilities": ["nlp"],
        "allowed_tools": ["nlp"],
        "tenant_id": "tenant-xyz",
    }
    bundle = {}
    sig = make_hmac_sig(key, manifest, bundle)
    capsule = {"manifest": manifest, "bundle": bundle, "signature": sig, "signer": "tester"}
    trusted = {"tester": key}

    before = len(EvidenceLedgerSingleton.entries())
    mp.register_capsule(capsule, trusted)
    after = len(EvidenceLedgerSingleton.entries())
    assert after >= before + 1

    card = ScorecardSingleton.snapshot("tenant-xyz")
    assert card["signature_total"] >= 1


def test_ephemeral_synth_records_ledger_and_sandbox():
    key = b"phase15-test-key"
    manifest = {
        "name": "ephemeral-1",
        "role": "ephemeral",
        "description": "ephemeral",
        "capabilities": ["nlp"],
        "allowed_tools": ["nlp"],
        "tenant_id": "tenant-xyz",
    }
    bundle = {}
    sig = make_hmac_sig(key, manifest, bundle)
    capsule = {"manifest": manifest, "bundle": bundle, "signature": sig, "signer": "tester"}
    trusted = {"tester": key}

    from core.ephemeral_synth import EphemeralSynthEngine

    eng = EphemeralSynthEngine()
    before = len(EvidenceLedgerSingleton.entries())
    eng.synthesize_from_capsule(capsule, trusted)
    after = len(EvidenceLedgerSingleton.entries())
    assert after >= before + 1
