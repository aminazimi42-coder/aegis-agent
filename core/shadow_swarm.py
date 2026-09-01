from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict

from core.ai_core import AICore


@dataclass
class ShadowResult:
    primary: Dict[str, Any]
    shadow: Dict[str, Any]
    divergence_score: float
    consensus: bool
    details: Dict[str, Any]


class ShadowSwarmRunner:
    """Run counterfactual shadow executions alongside the primary swarm.

    The runner compares primary outputs with a shadow execution (which may be
    configured to run with adversarial parameters) and computes a divergence
    score plus a simple consensus boolean.
    """

    def __init__(
        self,
        comparator: Callable[[Dict[str, Any], Dict[str, Any]], float] | None = None,
    ) -> None:
        self.ai_core = AICore()
        # comparator(primary, shadow) -> divergence 0.0-1.0
        self.comparator = comparator or self._default_comparator

    def _default_comparator(self, primary: Dict[str, Any], shadow: Dict[str, Any]) -> float:
        # Simple token-difference based proxy: normalized absolute difference of response lengths
        p = len(str(primary.get("response", "")))
        s = len(str(shadow.get("response", "")))
        if p == 0 and s == 0:
            return 0.0
        return min(1.0, abs(p - s) / max(1, max(p, s)))

    def execute_and_compare(
        self,
        task: str,
        *,
        shadow_modifier: Callable[[str], str] | None = None,
    ) -> ShadowResult:
        """Execute primary swarm and shadow swarm, then compare outputs.

        shadow_modifier, if provided, transforms the task into a counterfactual
        input for shadow execution (e.g., adversarial prompt perturbation).
        """
        start = time.time()
        primary = self.ai_core.dispatch(task)

        shadow_input = shadow_modifier(task) if shadow_modifier else task + " (shadow)"
        shadow = self.ai_core.dispatch(shadow_input)

        divergence = float(self.comparator(primary, shadow))
        consensus = divergence < 0.15

        details = {
            "primary_len": len(str(primary.get("response", ""))),
            "shadow_len": len(str(shadow.get("response", ""))),
            "elapsed_ms": (time.time() - start) * 1000.0,
        }

        return ShadowResult(
            primary=primary,
            shadow=shadow,
            divergence_score=round(divergence, 6),
            consensus=consensus,
            details=details,
        )


ShadowRunner = ShadowSwarmRunner
