from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence


class ToolTokenError(ValueError):
    """Base error for invalid tool tokens."""


class ToolTokenExpiredError(ToolTokenError, PermissionError):
    """Raised when a tool token has expired."""


class TokenScopeError(PermissionError):
    """Raised when a tool token lacks the required capability or scope."""


@dataclass(frozen=True)
class ToolAccessToken:
    """A short-lived capability token granting limited access to a tool."""

    tenant_id: str
    task_id: str
    tool_name: str
    capabilities: tuple[str, ...]
    issued_at: float
    expires_at: float
    token_id: str

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def allows(self, *, tool_name: str | None = None, required_capabilities: Sequence[str] | None = None, tenant_id: str | None = None, task_id: str | None = None) -> bool:
        if tool_name is not None and self.tool_name != tool_name:
            return False
        if tenant_id is not None and self.tenant_id != tenant_id:
            return False
        if task_id is not None and self.task_id != task_id:
            return False
        if required_capabilities:
            required = {str(capability).lower() for capability in required_capabilities}
            available = {str(capability).lower() for capability in self.capabilities}
            if not required.issubset(available):
                return False
        return not self.is_expired

    def to_payload(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "tenant_id": self.tenant_id,
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "capabilities": list(self.capabilities),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


class ToolTokenManager:
    """Issue and validate short-lived zero-trust tool tokens."""

    def __init__(self, ttl_seconds: int = 300, secret: str | None = None) -> None:
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.secret = secret or os.environ.get("AEGIS_TOOL_TOKEN_SECRET", "aegis-tool-token-secret")

    def _sign(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self.secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()

    def _serialize(self, payload: dict[str, Any]) -> str:
        signature = self._sign(payload)
        token = base64.urlsafe_b64encode(json.dumps({**payload, "signature": signature}, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")
        return token

    def _deserialize(self, token: str) -> dict[str, Any]:
        if not token:
            raise ToolTokenError("A tool token is required.")
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
            body = json.loads(decoded.decode("utf-8"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ToolTokenError("The tool token is malformed.") from exc

        expected = self._sign({k: v for k, v in body.items() if k != "signature"})
        if not hmac.compare_digest(body.get("signature", ""), expected):
            raise ToolTokenError("The tool token signature is invalid.")
        return body

    def issue_token(
        self,
        *,
        tenant_id: str,
        task_id: str,
        tool_name: str,
        capabilities: Iterable[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Issue a short-lived scoped token for a tool call."""
        normalized_capabilities = tuple(
            str(capability).lower() for capability in (capabilities or ["read"])
        )
        issued_at = time.time()
        expires_at = issued_at + float(ttl_seconds if ttl_seconds is not None else self.ttl_seconds)
        token_id = hashlib.sha256(
            f"{tenant_id}:{task_id}:{tool_name}:{issued_at}:{os.urandom(4).hex()}".encode("utf-8")
        ).hexdigest()[:32]
        payload = {
            "token_id": token_id,
            "tenant_id": str(tenant_id),
            "task_id": str(task_id),
            "tool_name": str(tool_name),
            "capabilities": list(normalized_capabilities),
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        return self._serialize(payload)

    def validate_token(
        self,
        token: str,
        *,
        tool_name: str,
        required_capabilities: Sequence[str] | None = None,
        tenant_id: str | None = None,
        task_id: str | None = None,
    ) -> ToolAccessToken:
        """Validate token authenticity, expiry, tenant scope, and required capabilities."""
        body = self._deserialize(token)
        access = ToolAccessToken(
            tenant_id=str(body["tenant_id"]),
            task_id=str(body["task_id"]),
            tool_name=str(body["tool_name"]),
            capabilities=tuple(str(capability).lower() for capability in body.get("capabilities", [])),
            issued_at=float(body["issued_at"]),
            expires_at=float(body["expires_at"]),
            token_id=str(body["token_id"]),
        )

        if access.is_expired:
            raise ToolTokenExpiredError("The tool token has expired.")

        if access.tool_name != str(tool_name):
            raise TokenScopeError("The tool token does not match the requested tool.")

        if tenant_id is not None and access.tenant_id != str(tenant_id):
            raise TokenScopeError("The tool token is not valid for this tenant.")

        if task_id is not None and access.task_id != str(task_id):
            raise TokenScopeError("The tool token is not valid for this task.")

        if required_capabilities:
            requested = {str(capability).lower() for capability in required_capabilities}
            available = {str(capability).lower() for capability in access.capabilities}
            if not requested.issubset(available):
                raise TokenScopeError(
                    f"The tool token lacks required capability. Missing: {sorted(requested - available)}"
                )

        return access

    def authorize_request(
        self,
        *,
        token: str | None,
        tool_name: str,
        required_capabilities: Sequence[str] | None = None,
        tenant_id: str | None = None,
        task_id: str | None = None,
    ) -> ToolAccessToken:
        if not token:
            raise PermissionError("A valid tool capability token is required.")
        return self.validate_token(
            token,
            tool_name=tool_name,
            required_capabilities=required_capabilities,
            tenant_id=tenant_id,
            task_id=task_id,
        )

    def authorize_headers(
        self,
        *,
        authorization: str | None,
        tool_name: str,
        required_capabilities: Sequence[str] | None = None,
        tenant_id: str | None = None,
        task_id: str | None = None,
    ) -> ToolAccessToken:
        token = None
        if authorization:
            if authorization.lower().startswith("bearer "):
                token = authorization.split(" ", 1)[1].strip()
            else:
                token = authorization.strip()
        return self.authorize_request(
            token=token,
            tool_name=tool_name,
            required_capabilities=required_capabilities,
            tenant_id=tenant_id,
            task_id=task_id,
        )

    def issue_for_tool(
        self,
        *,
        tenant_id: str,
        task_id: str,
        tool_name: str,
        capabilities: Iterable[str] | None = None,
    ) -> str:
        return self.issue_token(
            tenant_id=tenant_id,
            task_id=task_id,
            tool_name=tool_name,
            capabilities=capabilities,
        )


ZeroTrustToolTokenManager = ToolTokenManager


def issue_tool_token(*, tenant_id: str, task_id: str, tool_name: str, capabilities: Iterable[str] | None = None, ttl_seconds: int | None = None) -> str:
    return ToolTokenManager(ttl_seconds=ttl_seconds or 300).issue_token(
        tenant_id=tenant_id,
        task_id=task_id,
        tool_name=tool_name,
        capabilities=capabilities,
    )


def validate_tool_token(
    token: str,
    *,
    tool_name: str,
    required_capabilities: Sequence[str] | None = None,
    tenant_id: str | None = None,
    task_id: str | None = None,
) -> ToolAccessToken:
    return ToolTokenManager().validate_token(
        token,
        tool_name=tool_name,
        required_capabilities=required_capabilities,
        tenant_id=tenant_id,
        task_id=task_id,
    )


def build_token_expiry(ttl_seconds: int | None = None) -> datetime:
    seconds = float(ttl_seconds if ttl_seconds is not None else 300)
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
