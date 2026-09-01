from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable, Dict, List, Tuple


@dataclass
class SuperPrompt:
    name: str
    prompt: str
    # day_of_week: 0=Monday .. 6=Sunday
    day_of_week: int
    run_time: time


class SuperPromptEngine:
    """Store and execute weekly super-prompts on a fixed weekday/time.

    Execution requires a callback `executor(prompt)` that will be invoked for
    each due super-prompt. The engine itself is intentionally lightweight so
    it can be unit-tested without real schedulers.
    """

    def __init__(self) -> None:
        self._prompts: Dict[str, SuperPrompt] = {}

    def store(self, prompt: SuperPrompt) -> None:
        self._prompts[prompt.name] = prompt

    def remove(self, name: str) -> None:
        self._prompts.pop(name, None)

    def due_prompts(self, at: datetime) -> List[SuperPrompt]:
        weekday = (at.weekday() + 0)  # Monday=0
        now_t = at.time()
        due: List[SuperPrompt] = []
        for p in self._prompts.values():
            if (
                p.day_of_week == weekday
                and p.run_time.hour == now_t.hour
                and p.run_time.minute == now_t.minute
            ):
                due.append(p)
        return due

    def execute_due(self, at: datetime, executor: Callable[[str], None]) -> List[Tuple[str, str]]:
        results: List[Tuple[str, str]] = []
        for p in self.due_prompts(at):
            executor(p.prompt)
            results.append((p.name, p.prompt))
        return results
