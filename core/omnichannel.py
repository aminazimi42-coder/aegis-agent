from __future__ import annotations

import time
from typing import Any, Dict

from core.evidence_ledger import EvidenceLedgerSingleton
from core.usage_meter import UsageMeterSingleton


class OmnichannelBridge:
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        raise NotImplementedError()


class SlackBridge(OmnichannelBridge):
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        # Simulate send latency and return a fake message id
        time.sleep(0.001)
        msg_id = f"slk-{int(time.time()*1000)}"
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor="omnichannel/slack",
            action="send",
            payload={"recipient": recipient, "message_id": msg_id},
        )
        UsageMeterSingleton.record_usage(tenant_id, tokens=1, model="bridge/slack")
        return {"ok": True, "id": msg_id}


class EmailBridge(OmnichannelBridge):
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        time.sleep(0.001)
        msg_id = f"eml-{int(time.time()*1000)}"
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor="omnichannel/email",
            action="send",
            payload={"recipient": recipient, "message_id": msg_id},
        )
        UsageMeterSingleton.record_usage(tenant_id, tokens=1, model="bridge/email")
        return {"ok": True, "id": msg_id}


class BridgeManager:
    def __init__(self) -> None:
        self._bridges: Dict[str, OmnichannelBridge] = {}

    def register(self, name: str, bridge: OmnichannelBridge) -> None:
        self._bridges[name] = bridge

    def send(self, name: str, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        b = self._bridges.get(name)
        if not b:
            raise ValueError("bridge not found")
        return b.send(tenant_id, recipient, message)


BridgeManagerSingleton = BridgeManager()
