"""Operator idle session lock and local Keychain PIN (T220).

After the operator page is idle for ``AEGIS_SESSION_IDLE_SECONDS`` seconds
(default 900, min 60, max 86400) of no operator mutation, the session locks on
that tenant only.  Unlock is a local PIN stored in the macOS Keychain on
Darwin, or a mock store on CI/other platforms — the same store abstraction as
:mod:`core.llm_keychain`.

* ``lock(tenant_id)`` — force-lock this tenant now.
* ``unlock(tenant_id, pin)`` — unlock when the PIN matches.
* ``is_locked(tenant_id)`` — return ``True`` when locked.
* ``lock_state(tenant_id)`` — return ``{locked, locked_at}``.
* ``set_pin(tenant_id, pin)`` — store the PIN (min 6 digits).
* ``record_operator_activity(tenant_id)`` — reset the idle timer.
* ``forget_pin(tenant_id)`` — drop the PIN handle for this tenant.

Lockout after 5 wrong PINs for 5 minutes — a typed deny with code
``PIN_LOCKOUT`` and a ``retry_after`` seconds field.  A correct PIN
during lockout is also denied until the lockout window expires.

The PIN is never written into SQLite plaintext, audit JSONL, receipts, or
logs.  The PIN value is never printed or returned by any public function. The
lock is not macOS login and not a new identity product.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from core.llm_keychain import _KeychainStore, get_store

_SERVICE = "aegis-operator-session"
_ACCOUNT_PREFIX = ""  # account == tenant_id exactly (T220)

_idle_lock = threading.Lock()

# In-memory lock state: tenant_id → locked_at (ISO str).
# Persisted on the session receipt so a restart preserves the lock.
_locked_at: dict[str, str] = {}

# In-memory last-activity timestamp: tenant_id → ISO str of last mutation.
_last_activity: dict[str, str] = {}

# Lockout state: tenant_id → (failures int, lockout_until ISO str | None)
_lockout: dict[str, dict[str, Any]] = {}

_MAX_FAILURES = 5
_LOCKOUT_SECONDS = 300  # 5 minutes


def _idle_seconds() -> int:
    """Return the configured idle timeout in seconds.

    Default 900 (15 minutes).  Min 60, max 86400.
    """
    raw = os.getenv("AEGIS_SESSION_IDLE_SECONDS", "900")
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return 900
    if val < 60:
        return 60
    if val > 86400:
        return 86400
    return val


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _account(tenant_id: str) -> str:
    """Return the Keychain account name for *tenant_id* (T220: bare tenant_id)."""
    return _ACCOUNT_PREFIX + tenant_id


def _persist_lock(tenant_id: str, locked_at: str | None) -> None:
    """Persist the lock state on the session receipt."""
    try:
        from core.session_receipt import read_session_receipt, write_session_receipt

        receipt = read_session_receipt(tenant_id)
        write_session_receipt(
            tenant_id,
            session_id=receipt.get("session_id") if receipt else None,
            last_event=(
                "lock" if locked_at
                else (receipt.get("last_event", "propose") if receipt else "propose")
            ),
            last_action_id=receipt.get("last_action_id", "") if receipt else "",
            last_reject_reason=receipt.get("last_reject_reason", "") if receipt else "",
            last_task=receipt.get("last_task", "") if receipt else "",
            quiet_mode=receipt.get("quiet_mode", False) if receipt else False,
        )
    except Exception:
        pass


def _read_persisted_lock(tenant_id: str) -> str | None:
    """Read the persisted locked_at from the session receipt directory."""
    try:
        from core.twin_local_view import data_root

        root = data_root()
        lock_file = root / "session_locks" / f"{tenant_id}.lock"
        if lock_file.is_file():
            return lock_file.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass
    return None


def _write_persisted_lock(tenant_id: str, locked_at: str | None) -> None:
    """Write (or remove) the persisted lock file under AEGIS_DATA_DIR."""
    try:
        from core.twin_local_view import cage_path, data_root

        root = data_root()
        lock_dir = cage_path(root / "session_locks")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / f"{tenant_id}.lock"
        if locked_at:
            lock_file.write_text(locked_at + "\n", encoding="utf-8")
        else:
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        pass


def _check_idle_and_auto_lock(tenant_id: str) -> None:
    """Auto-lock the tenant if idle time has elapsed since last activity."""
    with _idle_lock:
        if tenant_id in _locked_at:
            return  # Already locked.
        last = _last_activity.get(tenant_id)
        if last is None:
            last = _read_persisted_lock(tenant_id)
            if last:
                _locked_at[tenant_id] = last
                return
            # No activity yet and no persisted lock — not locked.
            return
        try:
            last_dt = datetime.fromisoformat(last)
        except (ValueError, TypeError):
            return
        elapsed = datetime.now(timezone.utc) - last_dt
        threshold = timedelta(seconds=_idle_seconds())
        if elapsed >= threshold:
            locked_at = _now()
            _locked_at[tenant_id] = locked_at
            _write_persisted_lock(tenant_id, locked_at)


def record_operator_activity(tenant_id: str) -> None:
    """Record an operator mutation for *tenant_id* and reset the idle timer."""
    with _idle_lock:
        _last_activity[tenant_id] = _now()
        # If the tenant was locked, recording activity does NOT unlock —
        # only the correct PIN unlocks.  Activity just resets the timer
        # so the lock does not re-engage immediately after unlock.


def _lockout_active(tenant_id: str) -> str | None:
    """Return the lockout_until ISO str if lockout is active, else None."""
    state = _lockout.get(tenant_id)
    if not state:
        return None
    lockout_until = state.get("lockout_until")
    if not lockout_until:
        return None
    try:
        until_dt = datetime.fromisoformat(lockout_until)
    except (ValueError, TypeError):
        _lockout.pop(tenant_id, None)
        return None
    if datetime.now(timezone.utc) >= until_dt:
        # Lockout expired — clear it.
        _lockout.pop(tenant_id, None)
        return None
    return lockout_until


def _lockout_retry_after(tenant_id: str) -> int:
    """Return seconds remaining in the lockout window (0 if expired)."""
    until = _lockout_active(tenant_id)
    if not until:
        return 0
    try:
        until_dt = datetime.fromisoformat(until)
    except (ValueError, TypeError):
        return 0
    delta = until_dt - datetime.now(timezone.utc)
    return max(1, int(delta.total_seconds()))


def _record_failure(tenant_id: str) -> None:
    """Record a failed PIN attempt; engage lockout after _MAX_FAILURES."""
    state = _lockout.setdefault(tenant_id, {"failures": 0, "lockout_until": None})
    state["failures"] = state.get("failures", 0) + 1
    if state["failures"] >= _MAX_FAILURES:
        until = (datetime.now(timezone.utc) + timedelta(seconds=_LOCKOUT_SECONDS)).isoformat()
        state["lockout_until"] = until


def _clear_lockout(tenant_id: str) -> None:
    """Clear lockout state for *tenant_id* on a successful unlock."""
    _lockout.pop(tenant_id, None)


def is_locked(tenant_id: str) -> bool:
    """Return ``True`` when the session is locked for *tenant_id*."""
    _check_idle_and_auto_lock(tenant_id)
    with _idle_lock:
        if tenant_id in _locked_at:
            return True
        persisted = _read_persisted_lock(tenant_id)
        if persisted:
            _locked_at[tenant_id] = persisted
            return True
        return False


def lock_state(tenant_id: str) -> dict[str, Any]:
    """Return ``{locked, locked_at}`` for *tenant_id*."""
    _check_idle_and_auto_lock(tenant_id)
    with _idle_lock:
        locked_at = _locked_at.get(tenant_id)
        if locked_at is None:
            persisted = _read_persisted_lock(tenant_id)
            if persisted:
                _locked_at[tenant_id] = persisted
                locked_at = persisted
        return {
            "tenant_id": tenant_id,
            "locked": bool(locked_at),
            "locked_at": locked_at,
        }


def lock(tenant_id: str) -> dict[str, Any]:
    """Force-lock the session for *tenant_id* now."""
    with _idle_lock:
        locked_at = _now()
        _locked_at[tenant_id] = locked_at
        _write_persisted_lock(tenant_id, locked_at)
    return {
        "tenant_id": tenant_id,
        "locked": True,
        "locked_at": locked_at,
        "code": "SESSION_LOCKED",
    }


def unlock(tenant_id: str, pin: str) -> dict[str, Any]:
    """Unlock the session for *tenant_id* when *pin* matches the stored PIN.

    Lockout after 5 wrong PINs for 5 minutes — a typed deny with code
    ``PIN_LOCKOUT`` and a ``retry_after`` seconds field.  A correct PIN
    during lockout is also denied until the lockout window expires.

    The PIN value is never returned or logged.
    """
    _check_idle_and_auto_lock(tenant_id)
    with _idle_lock:
        if tenant_id not in _locked_at:
            persisted = _read_persisted_lock(tenant_id)
            if not persisted:
                # Not locked — nothing to unlock.
                return {
                    "tenant_id": tenant_id,
                    "locked": False,
                    "unlocked": False,
                    "code": "NOT_LOCKED",
                }
            _locked_at[tenant_id] = persisted
        # Check lockout first — even a correct PIN is denied during lockout.
        lockout_until = _lockout_active(tenant_id)
        if lockout_until:
            return {
                "tenant_id": tenant_id,
                "locked": True,
                "unlocked": False,
                "code": "PIN_LOCKOUT",
                "retry_after": _lockout_retry_after(tenant_id),
            }
        if not pin or not pin.strip():
            return {
                "tenant_id": tenant_id,
                "locked": True,
                "unlocked": False,
                "code": "PIN_REQUIRED",
            }
        store: _KeychainStore = get_store()
        stored = store.get(_SERVICE, _account(tenant_id))
        if stored is None or not stored.strip():
            return {
                "tenant_id": tenant_id,
                "locked": True,
                "unlocked": False,
                "code": "PIN_NOT_SET",
            }
        if pin.strip() != stored.strip():
            _record_failure(tenant_id)
            # Check if this triggered a lockout.
            if _lockout.get(tenant_id, {}).get("lockout_until"):
                return {
                    "tenant_id": tenant_id,
                    "locked": True,
                    "unlocked": False,
                    "code": "PIN_LOCKOUT",
                    "retry_after": _lockout_retry_after(tenant_id),
                }
            return {
                "tenant_id": tenant_id,
                "locked": True,
                "unlocked": False,
                "code": "WRONG_PIN",
            }
        # Correct PIN — unlock.
        _locked_at.pop(tenant_id, None)
        _write_persisted_lock(tenant_id, None)
        _clear_lockout(tenant_id)
        # Reset the idle timer on unlock.
        _last_activity[tenant_id] = _now()
        return {
            "tenant_id": tenant_id,
            "locked": False,
            "unlocked": True,
            "code": "SESSION_UNLOCKED",
        }


def set_pin(tenant_id: str, pin: str) -> dict[str, Any]:
    """Set the local PIN for *tenant_id*.

    The PIN must be at least 6 digits (numeric characters only).  Stored via
    the existing T196 Keychain helper.  Never written into SQLite plaintext.
    Never logged.  Never returned.
    """
    if not pin or not pin.strip():
        return {
            "tenant_id": tenant_id,
            "code": "PIN_EMPTY",
        }
    stripped = pin.strip()
    if len(stripped) < 6 or not stripped.isdigit():
        return {
            "tenant_id": tenant_id,
            "code": "PIN_INVALID",
        }
    store: _KeychainStore = get_store()
    store.set(_SERVICE, _account(tenant_id), stripped)
    return {
        "tenant_id": tenant_id,
        "code": "PIN_SET",
    }


def has_pin(tenant_id: str) -> bool:
    """Return ``True`` when a PIN is set for *tenant_id*."""
    store: _KeychainStore = get_store()
    stored = store.get(_SERVICE, _account(tenant_id))
    return stored is not None and bool(stored.strip())


def forget_pin(tenant_id: str) -> dict[str, Any]:
    """Drop the PIN handle for *tenant_id* and clear the lock.

    Neighbor tenants are never touched.  The PIN is removed from the
    Keychain/mock store.  The lock is also cleared.
    """
    with _idle_lock:
        _locked_at.pop(tenant_id, None)
        _last_activity.pop(tenant_id, None)
        _lockout.pop(tenant_id, None)
        _write_persisted_lock(tenant_id, None)
    # Remove the PIN from the store.  The store interface does not have a
    # delete method, so we set it to an empty string which the unlock path
    # treats as not-set (store.get returns "" which is falsy after strip).
    store: _KeychainStore = get_store()
    stored = store.get(_SERVICE, _account(tenant_id))
    if stored is not None:
        # MockKeychain stores in a dict; we can clear by setting empty.
        # DarwinKeychain uses the security CLI which does not have a
        # delete-generic-password via the same get/set interface here,
        # so we set empty which the unlock check treats as not-set.
        store.set(_SERVICE, _account(tenant_id), "")
    return {
        "tenant_id": tenant_id,
        "cleared": True,
        "code": "PIN_FORGOTTEN",
    }


def reset_for_tests() -> None:
    """Clear all in-memory state — test helper only."""
    with _idle_lock:
        _locked_at.clear()
        _last_activity.clear()
        _lockout.clear()
