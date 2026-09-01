from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any


class TenantMemoryVault:
    """Store encrypted, tenant-scoped memory with TTL and namespace isolation."""

    def __init__(self, default_ttl_seconds: int = 3600, master_key: str | None = None) -> None:
        self.default_ttl_seconds = max(0, int(default_ttl_seconds))
        self.master_key = master_key or os.environ.get(
            "AEGIS_TENANT_MEMORY_KEY",
            "aegis-tenant-memory-key",
        )
        self._vault: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    @staticmethod
    def _normalize_tenant(tenant_id: str | None) -> str:
        tenant = str(tenant_id or "default").strip()
        return tenant or "default"

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str:
        return str(namespace or "default").strip() or "default"

    @staticmethod
    def _normalize_key(key: str | None) -> str:
        key_name = str(key or "").strip()
        if not key_name:
            raise ValueError("Memory keys cannot be empty.")
        return key_name

    def _derive_key(self) -> bytes:
        return hashlib.sha256(self.master_key.encode("utf-8")).digest()

    def _encrypt(self, value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = self._derive_key()
        encrypted = bytes(b ^ key[index % len(key)] for index, b in enumerate(payload))
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def _decrypt(self, payload: str) -> Any:
        try:
            encrypted = base64.urlsafe_b64decode(payload.encode("utf-8"))
        except ValueError as exc:
            raise ValueError("The memory payload is not valid base64 data.") from exc
        key = self._derive_key()
        decrypted = bytes(b ^ key[index % len(key)] for index, b in enumerate(encrypted))
        try:
            return json.loads(decrypted.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("The decrypted memory payload is malformed.") from exc

    def _purge_expired(self, tenant_id: str, namespace: str) -> None:
        tenant_bucket = self._vault.get(tenant_id, {})
        namespace_bucket = tenant_bucket.get(namespace, {})
        now = time.time()
        expired_keys = [
            key
            for key, value in namespace_bucket.items()
            if value["expires_at"] <= now
        ]
        for key in expired_keys:
            del namespace_bucket[key]

        if not namespace_bucket:
            tenant_bucket.pop(namespace, None)
        if not tenant_bucket:
            self._vault.pop(tenant_id, None)

    def store(
        self,
        *,
        tenant_id: str,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        tenant_key = self._normalize_tenant(tenant_id)
        namespace_key = self._normalize_namespace(namespace)
        memory_key = self._normalize_key(key)

        ttl = self.default_ttl_seconds if ttl_seconds is None else max(0, int(ttl_seconds))
        expires_at = time.time() + ttl if ttl > 0 else time.time()

        bucket = self._vault.setdefault(tenant_key, {}).setdefault(namespace_key, {})
        bucket[memory_key] = {
            "value": self._encrypt(value),
            "expires_at": expires_at,
            "namespace": namespace_key,
            "tenant_id": tenant_key,
        }
        return bucket[memory_key]

    def read(
        self,
        tenant_id: str,
        key: str,
        *,
        namespace: str = "default",
    ) -> Any:
        tenant_key = self._normalize_tenant(tenant_id)
        namespace_key = self._normalize_namespace(namespace)
        memory_key = self._normalize_key(key)

        bucket = self._vault.get(tenant_key, {}).get(namespace_key, {})
        if memory_key not in bucket:
            for other_tenant, tenant_bucket in self._vault.items():
                if other_tenant == tenant_key:
                    continue
                if memory_key in tenant_bucket.get(namespace_key, {}):
                    raise PermissionError(
                        "Memory access denied: the requested key is scoped to a different tenant."
                    )
            raise KeyError(
                f"Memory key '{memory_key}' is not present in namespace '{namespace_key}'."
            )

        entry = bucket[memory_key]
        if entry["expires_at"] <= time.time():
            del bucket[memory_key]
            raise KeyError(f"Memory key '{memory_key}' has expired.")

        return self._decrypt(entry["value"])

    def delete(
        self,
        tenant_id: str,
        key: str,
        *,
        namespace: str = "default",
    ) -> bool:
        tenant_key = self._normalize_tenant(tenant_id)
        namespace_key = self._normalize_namespace(namespace)
        memory_key = self._normalize_key(key)
        bucket = self._vault.get(tenant_key, {}).get(namespace_key, {})
        if memory_key not in bucket:
            return False
        del bucket[memory_key]
        return True

    def snapshot(self, tenant_id: str | None = None) -> dict[str, Any]:
        target_tenant = self._normalize_tenant(tenant_id)
        tenant_bucket = self._vault.get(target_tenant, {})
        snapshot: dict[str, Any] = {}
        for namespace_key, namespace_bucket in tenant_bucket.items():
            snapshot[namespace_key] = {
                key: {"value": self._decrypt(entry["value"]), "expires_at": entry["expires_at"]}
                for key, entry in namespace_bucket.items()
            }
        return snapshot

    def authorize_access(
        self,
        tenant_id: str,
        key: str,
        *,
        namespace: str = "default",
    ) -> bool:
        tenant_key = self._normalize_tenant(tenant_id)
        namespace_key = self._normalize_namespace(namespace)
        memory_key = self._normalize_key(key)
        bucket = self._vault.get(tenant_key, {}).get(namespace_key, {})
        if memory_key not in bucket:
            return False
        if bucket[memory_key]["expires_at"] <= time.time():
            del bucket[memory_key]
            return False
        return True

    def __contains__(self, item: tuple[str, str, str] | str) -> bool:
        if isinstance(item, str):
            return any(item in tenant_namespace for tenant_namespace in self._vault.values())
        if len(item) != 3:
            return False
        tenant_id, namespace, key = item
        return self.authorize_access(tenant_id, key, namespace=namespace)


TenantMemory = TenantMemoryVault
