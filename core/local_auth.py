"""Optional local biometric unlock adapter (T226).

Touch ID is optional *after* the T220/T222 session lock + Keychain PIN.
On Darwin the adapter may call LocalAuthentication (``LAContext``); in CI
and on Linux the adapter is a typed mock that returns ``mock_ok``,
``mock_cancel``, or ``mock_unavailable`` as typed strings.

Failed or cancelled biometrics returns to the PIN — no silent unlock, no
face/voice capture or onboarding, and execution still requires a separate
Approve.

The mock result is controlled by ``AEGIS_TOUCH_ID_MOCK_RESULT`` (default
``mock_ok``) and mock availability by ``AEGIS_TOUCH_ID_MOCK_AVAILABLE``
(default ``1``).  Set ``AEGIS_TOUCH_ID_FORCE_MOCK=1`` to use the mock even
on Darwin (test/CI override).
"""

from __future__ import annotations

import os
import platform

_SUCCESS = {"mock_ok", "biometric_ok"}
_CANCEL = {"mock_cancel", "biometric_cancel"}
_UNAVAILABLE = {"mock_unavailable", "biometric_unavailable"}


def _is_darwin() -> bool:
    """Return True on macOS."""
    return platform.system() == "Darwin"


def _force_mock() -> bool:
    """Return True when the mock is forced (test/CI override)."""
    return os.getenv("AEGIS_TOUCH_ID_FORCE_MOCK", "0") == "1"


def is_available() -> bool:
    """Return True when Touch ID (Darwin) or the mock (CI/Linux) is available.

    On Darwin the adapter checks ``LAContext.canEvaluatePolicy:error:`` when
    PyObjC is installed; on CI/Linux the mock reports available unless
    ``AEGIS_TOUCH_ID_MOCK_AVAILABLE=0``.
    """
    if _is_darwin() and not _force_mock():
        return _darwin_biometry_available()
    # CI/Linux mock — available unless explicitly disabled.
    return os.getenv("AEGIS_TOUCH_ID_MOCK_AVAILABLE", "1") != "0"


def _darwin_biometry_available() -> bool:
    """Check Darwin biometry availability via LAContext (optional)."""
    try:
        import objc  # noqa: F401  — presence check
        from LocalAuthentication import LAContext  # type: ignore
    except ImportError:
        return False
    try:
        ctx = LAContext.new()
        # LAPolicyDeviceOwnerAuthenticationWithBiometrics == 2
        ret = ctx.canEvaluatePolicy_error_(2, None)
        if isinstance(ret, tuple):
            return bool(ret[0])
        return bool(ret)
    except Exception:
        return False


def authenticate(reason: str = "unlock session") -> str:
    """Authenticate via Touch ID (Darwin) or the typed mock (CI/Linux).

    Returns one of:
    * ``"biometric_ok"`` / ``"mock_ok"`` — success
    * ``"biometric_cancel"`` / ``"mock_cancel"`` — user cancelled
    * ``"biometric_unavailable"`` / ``"mock_unavailable"`` — not available

    On Darwin this calls ``LAContext.evaluatePolicy:localizedReason:reply:``;
    on CI/Linux it returns the mock result controlled by
    ``AEGIS_TOUCH_ID_MOCK_RESULT`` (default ``mock_ok``).
    """
    if _is_darwin() and not _force_mock():
        return _darwin_authenticate(reason)
    return os.getenv("AEGIS_TOUCH_ID_MOCK_RESULT", "mock_ok")


def _darwin_authenticate(reason: str) -> str:
    """Darwin Touch ID via LAContext (optional, requires PyObjC)."""
    try:
        import objc  # noqa: F401
        from LocalAuthentication import LAContext  # type: ignore
    except ImportError:
        return "biometric_unavailable"
    try:
        ctx = LAContext.new()
        ret = ctx.canEvaluatePolicy_error_(2, None)
        if isinstance(ret, tuple):
            can = bool(ret[0])
        else:
            can = bool(ret)
        if not can:
            return "biometric_unavailable"
    except Exception:
        return "biometric_unavailable"

    import threading

    done = threading.Event()
    box: list[str] = ["biometric_unavailable"]

    def _reply(success: bool, error: object) -> None:
        if success:
            box[0] = "biometric_ok"
        else:
            box[0] = "biometric_cancel"
        done.set()

    try:
        ctx.evaluatePolicy_localizedReason_reply_(2, reason, _reply)
        done.wait(timeout=30)
    except Exception:
        return "biometric_unavailable"
    return box[0]


def is_success(result: str) -> bool:
    """Return True when *result* is a success typed string."""
    return result in _SUCCESS


def is_cancel(result: str) -> bool:
    """Return True when *result* is a cancel typed string."""
    return result in _CANCEL


def is_unavailable(result: str) -> bool:
    """Return True when *result* is an unavailable typed string."""
    return result in _UNAVAILABLE
