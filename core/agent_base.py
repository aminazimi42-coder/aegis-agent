from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Base abstraction for all specialist agents in the platform."""

    name: str = "BaseAgent"

    @abstractmethod
    def handle(self, task: str) -> str:
        """Process a task and return a textual response."""
        raise NotImplementedError
