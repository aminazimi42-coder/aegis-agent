"""LLM tool cage and structured completion with secret redaction.

The model may only propose structured work inside an allowlist. It cannot
claim an external action happened and cannot invoke a tool outside the cage.

Secret values from :data:`SECRET_ENV_KEYS` are redacted before the prompt
reaches the provider, and every ``complete_safe`` call leaves an auditable
ledger row when the ledger is available.
"""

from __future__ import annotations

import os
from typing import Any

from core.llm_provider import HttpProvider, get_provider

ALLOWED_TOOLS: tuple[str, ...] = (
    "weekly_digest",
    "render_work_products",
    "propose_actions",
)

FORBIDDEN_CLAIMS: tuple[str, ...] = (
    "transferred funds",
    "pushed to origin",
    "payment sent",
    "email sent",
)

SECRET_ENV_KEYS: tuple[str, ...] = (
    "AEGIS_LLM_API_KEY",
    "AEGIS_GITHUB_TOKEN",
)


def redact_secrets(text: str) -> str:
    """Replace every occurrence of a set secret env value (len >= 8) with ``***``.

    Only values that are currently set in ``os.environ`` and are at least
    8 characters long are redacted, so short or unset placeholders are
    left untouched.
    """
    for key in SECRET_ENV_KEYS:
        val = os.environ.get(key)
        if val and len(val) >= 8:
            text = text.replace(val, "***")
    return text


def _parse_tool(text: str) -> str:
    """Extract tool name from a line like ``TOOL:<name>`` if present."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("TOOL:"):
            return stripped[len("TOOL:"):].strip()
    return ""


def _ledger_best_effort(tenant_id: str, result: dict[str, Any]) -> None:
    """Append a best-effort ledger entry; never raise."""
    try:
        from core.evidence_ledger import EvidenceLedger

        EvidenceLedger().append_entry(
            tenant_id=tenant_id,
            actor="llm_safety",
            action="llm_complete_safe",
            payload={
                "tenant_id": tenant_id,
                "model": result["model"],
                "ok": result["ok"],
                "tool": result["tool"],
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
            },
        )
    except Exception:
        pass


def complete_safe(
    prompt: str,
    *,
    tenant_id: str,
    model: str = "aegis-cheap",
    max_tokens: int = 128,
) -> dict[str, Any]:
    """Call the configured LLM provider and parse a structured tool.

    Returns a dict with keys: text, model, prompt_tokens,
    completion_tokens, total_tokens, tool, ok.

    The prompt is redacted with :func:`redact_secrets` before being sent
    to the provider so that secret API-key or token values never reach
    the model.

    If the provider response contains a ``TOOL:<name>`` line and that
    name is not in :data:`ALLOWED_TOOLS`, ``ok`` is ``False`` and
    ``text`` is replaced with ``"rejected: tool not allowed"``.

    After the completion (whether ``ok`` is True or False), a best-effort
    ledger entry is recorded via :class:`EvidenceLedger` with the action
    ``"llm_complete_safe"``. The ledger payload contains no raw secret
    values. If the ledger is unavailable or the append fails the
    completion result is still returned unchanged.

    After the provider returns, token usage is persisted via
    :func:`core.twin_persist.add_spend` so a process restart keeps the
    cumulative burn.  If ``add_spend`` raises, the completion result is
    still returned unchanged.

    This module never calls any downstream action runner; it only
    reads provider output and classifies it against the allowlist.
    """
    safe_prompt = redact_secrets(prompt)

    # If the token budget is exhausted, do not call the provider at all.
    if os.environ.get("AEGIS_LLM_BUDGET_EXHAUSTED") == "1":
        result = {
            "text": "rejected: budget exhausted",
            "model": model,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "tool": "",
            "ok": False,
            "provider_kind": "echo",
        }
        _ledger_best_effort(tenant_id, result)
        return result

    provider = get_provider()
    provider_kind = "http" if isinstance(provider, HttpProvider) else "echo"
    raw = provider.complete(safe_prompt, model=model, max_tokens=max_tokens)

    # Persist token spend so a restart keeps the burn.
    try:
        from core.twin_persist import add_spend

        add_spend(tenant_id, float(raw.get("total_tokens", 0)))
    except Exception:
        pass

    text = str(raw.get("text", ""))
    tool = _parse_tool(text)

    ok = True
    if tool and tool not in ALLOWED_TOOLS:
        ok = False
        # tool stays as the rejected name
        text = "rejected: tool not allowed"

    # Reject claims of external actions that the model cannot have performed.
    if ok and any(phrase in text.lower() for phrase in FORBIDDEN_CLAIMS):
        ok = False
        text = "rejected: external action claim"

    result = {
        "text": text,
        "model": raw.get("model", model),
        "prompt_tokens": raw.get("prompt_tokens", 0),
        "completion_tokens": raw.get("completion_tokens", 0),
        "total_tokens": raw.get("total_tokens", 0),
        "tool": tool,
        "ok": ok,
        "provider_kind": provider_kind,
    }
    if provider_kind == "http":
        result["fallback_label"] = "http-fallback"

    _ledger_best_effort(tenant_id, result)
    return result
