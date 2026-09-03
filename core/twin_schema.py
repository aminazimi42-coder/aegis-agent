"""Cognitive-twin profile schema for the Aegis Agent platform.

A ``TwinProfile`` is the versioned, fingerprinted output of the day-zero
cognitive interview.  The fingerprint is a deterministic SHA-256 over the
canonical JSON of the *layer* fields only (timestamps are excluded so that
re-creating a profile at a different time still yields the same hash).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# Canonical order of layer fields used for the fingerprint.
_LAYER_FIELDS: tuple[str, ...] = (
    "role",
    "decision_style",
    "tools",
    "risk_posture",
    "work_ethics",
    "repositories",
)


@dataclass
class TwinProfile:
    """Versioned cognitive profile of a tenant."""

    tenant_id: str
    profile_id: str
    version: int = 1
    consent: bool = False
    created_at: str = ""
    updated_at: str = ""
    # Layers
    role: str = ""
    decision_style: str = ""
    tools: str = ""
    risk_posture: str = ""
    work_ethics: str = ""
    repositories: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    # ------------------------------------------------------------------ #
    # Serialisation helpers
    # ------------------------------------------------------------------ #

    def layers(self) -> dict[str, Any]:
        """Return only the cognitive-layer fields in canonical order."""
        return {f: getattr(self, f) for f in _LAYER_FIELDS}

    def fingerprint(self) -> str:
        """Return ``sha256`` of the canonical JSON of the layer fields."""
        canonical = json.dumps(self.layers(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON / SQLite storage."""
        data = asdict(self)
        data["fingerprint"] = self.fingerprint()
        return data

    # ------------------------------------------------------------------ #
    # Construction from raw layer values
    # ------------------------------------------------------------------ #

    @classmethod
    def from_layers(
        cls,
        tenant_id: str,
        profile_id: str,
        version: int,
        consent: bool,
        answers: dict[str, str],
    ) -> TwinProfile:
        """Build a ``TwinProfile`` from interview answers.

        ``answers`` is a mapping of question-id → raw text for each layer.
        """
        return cls(
            tenant_id=tenant_id,
            profile_id=profile_id,
            version=version,
            consent=consent,
            role=answers.get("q_role", ""),
            decision_style=answers.get("q_decision_style", ""),
            tools=answers.get("q_tools", ""),
            risk_posture=answers.get("q_risk", ""),
            work_ethics=answers.get("q_ethics", ""),
            repositories=answers.get("q_repos", ""),
        )


def compute_fingerprint(layers: dict[str, Any]) -> str:
    """Standalone helper: SHA-256 over canonical JSON of ``layers``."""
    canonical = json.dumps(layers, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
