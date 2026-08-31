from __future__ import annotations


class SecurityPolicy:
    """Minimal platform security scaffold with deterministic allow-list validation."""

    ALLOWED_AGENTS = {"Alina", "Kian", "Bita", "Aylin"}

    def is_allowed(self, agent_name: str) -> bool:
        return agent_name in self.ALLOWED_AGENTS

    def validate_task(self, task: str) -> str:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task input must be a non-empty string.")
        return task.strip()
