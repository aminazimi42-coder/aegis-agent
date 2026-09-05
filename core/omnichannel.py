from __future__ import annotations

from typing import Any, Dict

QUARANTINED = True


class OmnichannelBridge:
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        raise RuntimeError("quarantined")


class SlackBridge(OmnichannelBridge):
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        raise RuntimeError("quarantined")


class EmailBridge(OmnichannelBridge):
    def send(self, tenant_id: str, recipient: str, message: str) -> Dict[str, Any]:
        raise RuntimeError("quarantined")


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
