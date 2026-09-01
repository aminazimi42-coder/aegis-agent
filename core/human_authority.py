from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional


class ApprovalLevel(Enum):
    AUTO = auto()
    SINGLE_APPROVAL = auto()
    DUAL_APPROVAL = auto()
    DENY = auto()


@dataclass
class RiskProfile:
    score: float
    level: ApprovalLevel
    reason: str | None = None


class HumanAuthority:
    """Simple risk-weighted human authority evaluator.

    This is intentionally conservative and deterministic for unit testing:
    - low risk (score < 0.3) -> AUTO
    - medium risk (0.3 <= score < 0.7) -> SINGLE_APPROVAL
    - high risk (0.7 <= score < 0.95) -> DUAL_APPROVAL
    - critical (>= 0.95) -> DENY
    """

    def evaluate_risk(self, action: str, context: Dict[str, Any] | None = None) -> RiskProfile:
        context = context or {}
        # Base heuristics: longer tasks or ones with keywords get higher risk
        length_factor = min(1.0, len(action) / 200)
        keywords = ["delete", "remove", "exfiltrate", "transfer", "send", "publish"]
        keyword_factor = 0.35 if any(k in action.lower() for k in keywords) else 0.0
        tenant_sensitivity = 0.2 if context.get("tenant_sensitive") else 0.0

        score = min(1.0, length_factor + keyword_factor + tenant_sensitivity)

        if score < 0.3:
            level = ApprovalLevel.AUTO
        elif score < 0.7:
            level = ApprovalLevel.SINGLE_APPROVAL
        elif score < 0.95:
            level = ApprovalLevel.DUAL_APPROVAL
        else:
            level = ApprovalLevel.DENY

        reason = f"score={score:.2f} (len={len(action)},kw={keyword_factor},s={tenant_sensitivity})"
        return RiskProfile(score=score, level=level, reason=reason)

    def requires_approval(self, profile: RiskProfile) -> bool:
        return profile.level in (ApprovalLevel.SINGLE_APPROVAL, ApprovalLevel.DUAL_APPROVAL)

    def check_authorization(self, action: str, context: Optional[Dict[str, Any]] = None):
        profile = self.evaluate_risk(action, context)
        if profile.level == ApprovalLevel.DENY:
            raise PermissionError(f"Action denied by policy: {profile.reason}")
        return profile
