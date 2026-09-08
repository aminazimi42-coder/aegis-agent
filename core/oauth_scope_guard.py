"""Readonly OAuth scope guard (T118).

Allow only scopes that end with ``.readonly`` or are already the local
git-observe path.  Reject tokens that contain ``gmail.send``,
``calendar.events``, or any write scope before persisting.

No live OAuth client, no Keychain integration — this is a pure guard.
"""

from __future__ import annotations

# Scopes that always imply write access and must be rejected.
_WRITE_SCOPES: frozenset[str] = frozenset(
    {
        "gmail.send",
        "calendar.events",
    }
)

# The local git-observe path is allowed as a bare scope string.
_LOCAL_GIT_OBSERVE = "git-observe"


def is_readonly_scope(scope: str) -> bool:
    """Return ``True`` when *scope* is a readonly scope or the local observe path.

    A scope is readonly when:
    - it ends with ``.readonly``, **or**
    - it is exactly ``"git-observe"`` (the local observe path).
    """
    if not isinstance(scope, str) or not scope.strip():
        return False
    s = scope.strip()
    if s == _LOCAL_GIT_OBSERVE:
        return True
    return s.endswith(".readonly")


def contains_write_scope(scope: str) -> bool:
    """Return ``True`` when *scope* contains a write scope like ``gmail.send``.

    Scope strings are space-separated tokens.  A token matches a known write
    scope (e.g. ``gmail.send``, ``calendar.events``) exactly.
    """
    if not isinstance(scope, str) or not scope.strip():
        return False
    tokens = scope.strip().split()
    for tok in tokens:
        if tok in _WRITE_SCOPES:
            return True
    return False


def is_scope_allowed(scope: str) -> bool:
    """Return ``True`` when *scope* may be persisted.

    The scope is allowed when every token is readonly **and** no token
    is a known write scope.
    """
    if not isinstance(scope, str) or not scope.strip():
        return False
    if contains_write_scope(scope):
        return False
    tokens = scope.strip().split()
    return all(is_readonly_scope(tok) for tok in tokens)


def guard_scope(scope: str) -> str:
    """Validate *scope* and return it when allowed, or raise ``ValueError``.

    Raises ``ValueError("write scope rejected")`` when the scope contains
    a write scope (``gmail.send``, ``calendar.events``) or when a token is
    not readonly.
    """
    if contains_write_scope(scope):
        raise ValueError("write scope rejected")
    if not is_scope_allowed(scope):
        raise ValueError("write scope rejected")
    return scope
