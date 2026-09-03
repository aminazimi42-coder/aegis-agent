"""LLM tool cage and structured completion.

The model may only propose structured work inside an allowlist. It cannot
claim an external action happened and cannot invoke a tool outside the cage.
"""

from __future__ import annotations

from typing import Any

from core.llm_provider import get_provider

ALLOWED_TOOLS: tuple[str, ...] = (
    "weekly_digest",
    "render_work_products",
    "propose_actions",
)


def _parse_tool(text: str) -> str:
    """Extract tool name from a line like ``TOOL:<name>`` if present."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("TOOL:"):
            return stripped[len("TOOL:"):].strip()
    return ""


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

    If the provider response contains a ``TOOL:<name>`` line and that
    name is not in :data:`ALLOWED_TOOLS`, ``ok`` is ``False`` and
    ``text`` is replaced with ``"rejected: tool not allowed"``.

    This module never calls any downstream action runner; it only
    reads provider output and classifies it against the allowlist.
    """
    provider = get_provider()
    raw = provider.complete(prompt, model=model, max_tokens=max_tokens)

    text = str(raw.get("text", ""))
    tool = _parse_tool(text)

    ok = True
    if tool and tool not in ALLOWED_TOOLS:
        ok = False
        # tool stays as the rejected name
        text = "rejected: tool not allowed"

    return {
        "text": text,
        "model": raw.get("model", model),
        "prompt_tokens": raw.get("prompt_tokens", 0),
        "completion_tokens": raw.get("completion_tokens", 0),
        "total_tokens": raw.get("total_tokens", 0),
        "tool": tool,
        "ok": ok,
    }
