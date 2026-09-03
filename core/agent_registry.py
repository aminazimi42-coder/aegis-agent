from __future__ import annotations

from .types import AgentSpec

AGENT_REGISTRY: list[AgentSpec] = [
    AgentSpec(
        name="Alina",
        role="Strategic coordination",
        description="Responsible for orchestration, prioritization, and system-level decisions.",
        capabilities=["planning", "coordination", "routing"],
    ),
    AgentSpec(
        name="Kian",
        role="Operational execution",
        description="Responsible for fast execution and task flow management.",
        capabilities=["execution", "monitoring", "optimization"],
    ),
    AgentSpec(
        name="Bita",
        role="Analysis and synthesis",
        description="Responsible for structured reasoning and synthesis of inputs.",
        capabilities=["analysis", "synthesis", "reporting"],
    ),
    AgentSpec(
        name="Aylin",
        role="Quality and validation",
        description="Responsible for quality assurance, verification, and final checks.",
        capabilities=["validation", "quality", "review"],
    ),
    AgentSpec(
        name="Ahmad",
        role="Security and oversight",
        description=(
            "Responsible for security posture, KMS rotation oversight, "
            "and incident triage."
        ),
        capabilities=["security", "oversight", "governance", "kms"],
    ),
    AgentSpec(
        name="Amin",
        role="Finance and executive bridge",
        description=(
            "Responsible for token economy management, invoicing, "
            "and executive directives."
        ),
        capabilities=["finance", "invoicing", "settlement", "executive"],
    ),
]
