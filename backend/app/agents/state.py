"""Agent state definitions for Magezi supervisor routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRoute(Enum):
    """Possible routing destinations for student queries."""
    RAG = "rag"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    MATHEMATICS = "mathematics"
    CLARIFY = "clarify"
    ESCALATE = "escalate"


@dataclass
class RouteDecision:
    """Result of supervisor classification."""
    route: str  # "rag", "physics", "chemistry", etc.
    subject: str | None  # Detected subject
    confidence: float = 0.0
    reason: str = ""
    clarification: str | None = None
    suggested_tools: list[str] = field(default_factory=list)
