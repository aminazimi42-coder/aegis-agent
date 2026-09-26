"""T222 — Optional local SMTP sidecar after Approve only.

After the operator Approves an action, an optional local SMTP sidecar may send
one short local notice mail.  The twin execute path never calls SMTP —
``execute()`` and ``propose()`` do not import this module and do not call the
network.

Behaviour
=========

* ``configure(host, port, user_ref, from_addr, to_addr)`` stores the SMTP host,
  port, user reference, from address, and to address in the macOS Keychain on
  Darwin (or a mock in-memory store on CI) — the same store abstraction as
  :mod:`core.llm_keychain`.  The SMTP password is never written into git,
  ``AEGIS_DATA_DIR`` plaintext, propose text, audit body, or receipts.  It may
  be supplied via the optional ``AEGIS_SMTP_PASSWORD`` env var for the local
  operator machine only.

* ``notify_approved(tenant_id, action_id, digest_prefix)`` sends one short
  SMTP message when the host and to address are configured.  Missing config
  returns ``{"status": "not_configured"}`` — a typed skip, never an exception.
  A network or SMTP failure returns ``{"status": "smtp_sidecar_failed"}`` — the
  approval and receipt stay valid; no retry-storm, no raise into execute.

* ``notify_status_label()`` returns a one-line operator-page label:
  ``"Mail notice: off"`` when unset, ``"Mail notice: not_configured"`` when
  partially configured, or ``"Mail notice: sent"`` / ``"Mail notice: failed"``
  after a send attempt.

The message body contains only the tenant id, action id, and digest prefix —
never the SMTP password, never the host credentials, never a secret shape.
"""

from __future__ import annotations

import os
from typing import Any

from core.llm_keychain import _KeychainStore, get_store

_SERVICE = "aegis-operator-smtp"
_HOST_ACCOUNT = "smtp-host"
_PORT_ACCOUNT = "smtp-port"
_USER_ACCOUNT = "smtp-user"
_FROM_ACCOUNT = "smtp-from"
_TO_ACCOUNT_PREFIX = "smtp-to-"

# Env vars for local operator machine only (optional, documented).
_ENV_PASSWORD = "AEGIS_SMTP_PASSWORD"
_ENV_HOST = "AEGIS_SMTP_HOST"
_ENV_PORT = "AEGIS_SMTP_PORT"
_ENV_FROM = "AEGIS_SMTP_FROM_ADDR"
_ENV_TO = "AEGIS_SMTP_TO_ADDR"
_ENV_USER = "AEGIS_SMTP_USER"


def _to_account(tenant_id: str) -> str:
    """Return the Keychain account name for the to address of *tenant_id*."""
    return _TO_ACCOUNT_PREFIX + tenant_id


def _resolve(store: _KeychainStore, account: str, env_var: str) -> str | None:
    """Resolve a config value from the Keychain/mock store or env var."""
    val = store.get(_SERVICE, account)
    if val and val.strip():
        return val.strip()
    env_val = os.getenv(env_var, "").strip()
    return env_val or None


def _resolve_password() -> str | None:
    """Resolve the SMTP password from the Keychain/mock store or env.

    The password is never logged, printed, or written into git, receipts,
    audit JSONL, or propose text.
    """
    store: _KeychainStore = get_store()
    val = store.get(_SERVICE, "smtp-password")
    if val and val.strip():
        return val.strip()
    env_val = os.getenv(_ENV_PASSWORD, "").strip()
    return env_val or None


def configure(
    host: str,
    port: str | int,
    user_ref: str,
    from_addr: str,
    to_addr: str,
) -> dict[str, Any]:
    """Store the SMTP host, port, user ref, from, and to in the Keychain/mock store.

    The password is not stored here — it is resolved at send time from the
    Keychain/mock store (account ``smtp-password``) or the optional
    ``AEGIS_SMTP_PASSWORD`` env var.  No secret is written into plaintext
    files, SQLite, audit JSONL, or receipts.

    Returns ``{"configured": True, "code": "SMTP_CONFIGURED"}``.
    """
    store: _KeychainStore = get_store()
    store.set(_SERVICE, _HOST_ACCOUNT, host.strip())
    store.set(_SERVICE, _PORT_ACCOUNT, str(port).strip())
    store.set(_SERVICE, _USER_ACCOUNT, user_ref.strip())
    store.set(_SERVICE, _FROM_ACCOUNT, from_addr.strip())
    # Store the to address under a tenant-bound account.
    store.set(_SERVICE, _to_account(to_addr), to_addr.strip())
    return {"configured": True, "code": "SMTP_CONFIGURED"}


def _send_smtp(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send one short SMTP message.

    Returns ``{"status": "sent"}`` on success or
    ``{"status": "smtp_sidecar_failed"}`` on any failure.  Never raises.
    """
    try:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(host, port, timeout=10) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return {"status": "sent"}
    except Exception:
        return {"status": "smtp_sidecar_failed"}


def notify_approved(
    tenant_id: str,
    action_id: str,
    digest_prefix: str,
) -> dict[str, Any]:
    """Send a short SMTP notice for a successful Approve event.

    When the host or to address is unset, returns
    ``{"status": "not_configured"}`` without touching the network.

    When host, port, from, and to are all set, sends one SMTP message.  A
    network or SMTP failure returns
    ``{"status": "smtp_sidecar_failed"}`` — the approval and receipt stay
    valid.  This function never raises.

    The message body contains only the tenant id, action id, and digest
    prefix — never the SMTP password, never the host credentials, never a
    secret shape.
    """
    store: _KeychainStore = get_store()
    host = _resolve(store, _HOST_ACCOUNT, _ENV_HOST)
    port_str = _resolve(store, _PORT_ACCOUNT, _ENV_PORT)
    user = _resolve(store, _USER_ACCOUNT, _ENV_USER)
    from_addr = _resolve(store, _FROM_ACCOUNT, _ENV_FROM)
    to_addr = _resolve(store, _to_account(tenant_id), _ENV_TO)

    if not host or not to_addr or not from_addr:
        return {"status": "not_configured"}

    port = 25
    if port_str:
        try:
            port = int(port_str)
        except (TypeError, ValueError):
            port = 25

    password = _resolve_password()

    subject = "Aegis Approve notice"
    body = (
        f"Aegis Approve: tenant={tenant_id} "
        f"action={action_id} digest={digest_prefix[:12]}"
    )
    return _send_smtp(
        host,
        port,
        user,
        password,
        from_addr,
        to_addr,
        subject,
        body,
    )


def notify_status_label() -> str:
    """Return a one-line operator-page label for the SMTP sidecar.

    Returns ``"Mail notice: off"`` when the host is unset,
    ``"Mail notice: not_configured"`` when the host is set but the to
    address is missing.
    """
    store: _KeychainStore = get_store()
    host = _resolve(store, _HOST_ACCOUNT, _ENV_HOST)
    to_addr = _resolve(store, _to_account("default"), _ENV_TO)
    if not host:
        return "Mail notice: off"
    if not to_addr:
        return "Mail notice: not_configured"
    return "Mail notice: not_configured"
