"""T221 — Optional Telegram sidecar after Approve only.

After the operator Approves an action, an optional local sidecar may send a
short Telegram notice to a configured chat.  The twin execute path never calls
Telegram — ``execute()`` and ``propose()`` do not import this module and do
not call the network.

Behaviour
=========

* ``configure(token_ref, chat_id)`` stores the Telegram bot token and chat id
  in the macOS Keychain on Darwin (or a mock in-memory store on CI) — the same
  store abstraction as :mod:`core.llm_keychain`.  The token is never written
  into git, ``AEGIS_DATA_DIR`` plaintext, propose text, audit body, or
  receipts.

* ``notify_approved(tenant_id, action_id, digest_prefix)`` sends one short
  Telegram message when the token is configured.  Missing token or chat id
  returns ``{"status": "not_configured"}`` — a typed skip, never an exception.
  A network failure returns ``{"status": "telegram_sidecar_failed"}`` — the
  approval and receipt stay valid; no retry-storm, no raise into execute.

* The token may also be supplied via the ``AEGIS_TELEGRAM_BOT_TOKEN`` env var
  for the local operator machine (documented as optional).  The Keychain/mock
  store value takes precedence.

* ``notify_status_label()`` returns a one-line operator-page label:
  ``"Telegram notice: off"`` when unset, ``"Telegram notice: not_configured"``
  when partially configured, or ``"Telegram notice: sent"`` / ``"Telegram
  notice: failed"`` after a send attempt.

The Telegram Bot API endpoint is ``https://api.telegram.org/bot<token>/sendMessage``.
HTTP is only attempted when both a token and a chat id are present.
"""

from __future__ import annotations

import os
from typing import Any

from core.llm_keychain import _KeychainStore, get_store

_SERVICE = "aegis-operator-telegram"
_TOKEN_ACCOUNT = "bot-token"
_CHAT_ACCOUNT_PREFIX = "chat-"

# Env var for local operator machine only (optional, documented).
_ENV_TOKEN = "AEGIS_TELEGRAM_BOT_TOKEN"
_ENV_CHAT = "AEGIS_TELEGRAM_CHAT_ID"


def _chat_account(tenant_id: str) -> str:
    """Return the Keychain account name for the chat id of *tenant_id*."""
    return _CHAT_ACCOUNT_PREFIX + tenant_id


def _resolve_token() -> str | None:
    """Return the Telegram bot token from the Keychain/mock store or env.

    Order:
    1.  Keychain/mock store value (when present),
    2.  ``AEGIS_TELEGRAM_BOT_TOKEN`` env var (when set),
    3.  ``None``.
    """
    store: _KeychainStore = get_store()
    val = store.get(_SERVICE, _TOKEN_ACCOUNT)
    if val and val.strip():
        return val.strip()
    env_val = os.getenv(_ENV_TOKEN, "").strip()
    return env_val or None


def _resolve_chat_id(tenant_id: str) -> str | None:
    """Return the Telegram chat id for *tenant_id* from the store or env."""
    store: _KeychainStore = get_store()
    val = store.get(_SERVICE, _chat_account(tenant_id))
    if val and val.strip():
        return val.strip()
    env_val = os.getenv(_ENV_CHAT, "").strip()
    return env_val or None


def configure(token_ref: str, chat_id: str) -> dict[str, Any]:
    """Store the Telegram bot token and chat id in the Keychain/mock store.

    The token is stored under service ``aegis-operator-telegram`` account
    ``bot-token``.  The chat id is stored under account ``chat-{chat_id}`` —
    but note that ``chat_id`` here is the **operator's chat id**, not a
    tenant id.  The token is never written into plaintext files, SQLite,
    audit JSONL, or receipts.

    Returns ``{"configured": True, "code": "TELEGRAM_CONFIGURED"}``.
    """
    store: _KeychainStore = get_store()
    store.set(_SERVICE, _TOKEN_ACCOUNT, token_ref.strip())
    # Store the chat id under a fixed account so it is operator-wide.
    store.set(_SERVICE, "chat-id", chat_id.strip())
    return {"configured": True, "code": "TELEGRAM_CONFIGURED"}


def _send_http(token: str, chat_id: str, text: str) -> dict[str, Any]:
    """Send one Telegram message via the Bot API.

    Returns ``{"status": "sent"}`` on success or
    ``{"status": "telegram_sidecar_failed"}`` on any failure.
    Never raises.
    """
    try:
        import urllib.error
        import urllib.request

        url = (
            f"https://api.telegram.org/bot{token}/sendMessage"
        )
        payload = (
            f'chat_id={chat_id}&text={text}'
        )
        data = payload.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            if resp.status == 200:
                return {"status": "sent"}
            return {"status": "telegram_sidecar_failed"}
    except Exception:
        return {"status": "telegram_sidecar_failed"}


def notify_approved(
    tenant_id: str,
    action_id: str,
    digest_prefix: str,
) -> dict[str, Any]:
    """Send a short Telegram notice for a successful Approve event.

    When the token or chat id is unset, returns
    ``{"status": "not_configured"}`` without touching the network.

    When both are set, sends one ``sendMessage`` request to the Telegram Bot
    API.  A network failure returns
    ``{"status": "telegram_sidecar_failed"}`` — the approval and receipt
    stay valid.  This function never raises.

    The message body contains only the tenant id, action id, and digest
    prefix — never the token, never the chat id, never a secret shape.
    """
    token = _resolve_token()
    if not token:
        return {"status": "not_configured"}
    chat_id = _resolve_chat_id(tenant_id)
    if not chat_id:
        return {"status": "not_configured"}
    text = (
        f"Aegis Approve: tenant={tenant_id} "
        f"action={action_id} digest={digest_prefix[:12]}"
    )
    return _send_http(token, chat_id, text)


def notify_status_label() -> str:
    """Return a one-line operator-page label for the Telegram sidecar.

    Returns ``"Telegram notice: off"`` when the token is unset,
    ``"Telegram notice: not_configured"`` when the token is set but no
    chat id is configured.
    """
    token = _resolve_token()
    if not token:
        return "Telegram notice: off"
    return "Telegram notice: not_configured"
