from __future__ import annotations

import re
from typing import Any


class SecurityPolicy:
    """Platform security scaffold with deterministic allow-list and injection protection."""

    ALLOWED_AGENTS = {"Alina", "Kian", "Bita", "Aylin", "Amin", "Ahmad"}
    THREAT_PATTERNS = (
        re.compile(r"(?i)(?:union\s+select|drop\s+table|insert\s+into|delete\s+from|alter\s+table|update\s+set)"),
        re.compile(r"(?i)(?:;\s*(?:drop|alter|truncate|delete|update|insert)\b|--\s*$|/\*|\*/)"),
        re.compile(r"(?i)(?:\bor\s+1\s*=\s*1\b|\bselect\b.*\bfrom\b)"),
        re.compile(r"(?i)(?:<\s*script|javascript:|onerror\s*=|onload\s*=|<\s*iframe|<\s*svg)"),
        re.compile(r"(?i)(?:\\x[0-9a-f]{2}|%27|%22|%3c|%3e)"),
    )

    def is_allowed(self, agent_name: str) -> bool:
        return agent_name in self.ALLOWED_AGENTS

    def _contains_threat(self, value: str) -> bool:
        normalized = " ".join(value.split())
        return any(pattern.search(normalized) for pattern in self.THREAT_PATTERNS)

    def validate_task(self, task: str) -> str:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task input must be a non-empty string.")

        cleaned = task.strip()
        if len(cleaned) > 2000:
            raise ValueError("Task input exceeds the maximum allowed size.")
        if self._contains_threat(cleaned):
            raise ValueError(
                "Task input contains suspicious content and was rejected "
                "by the security firewall."
            )
        return cleaned


def sanitize_payload(value: Any) -> Any:
    """Recursively sanitize payload values, rejecting suspicious agent task strings."""
    policy = SecurityPolicy()

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            sanitized[key] = sanitize_payload(item)
        if "task" in sanitized and isinstance(sanitized["task"], str):
            sanitized["task"] = policy.validate_task(sanitized["task"])
        return sanitized

    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]

    if isinstance(value, str):
        return policy.validate_task(value)

    return value
