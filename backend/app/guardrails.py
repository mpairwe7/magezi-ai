"""Safety guardrails for Magezi — OWASP LLM Top 10 defences.

Forked from URA Chatbot, adapted for education context.
- Input: prompt injection detection, content filtering
- Output: abstention check, grounding verification
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
ABSTENTION_THRESHOLD = float(os.getenv("ABSTENTION_THRESHOLD", "0.15"))

# Prompt injection patterns (OWASP LLM01)
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions?|prompts?|rules?)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"disregard\s+(everything|all|your)\s+",
    r"forget\s+(everything|all|your)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*you\s+are",
    r"<\s*system\s*>",
    r"\[\s*INST\s*\]",
    r"pretend\s+you('re|\s+are)\s+",
    r"act\s+as\s+(if\s+you('re|\s+are)|a\s+)",
    r"jailbreak",
    r"DAN\s+mode",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Content that should be blocked in an education context
_BLOCKED_CONTENT = [
    r"(how\s+to\s+)?(cheat|hack|steal|forge|fake)",
    r"(give\s+me\s+)?(exam\s+answers|test\s+answers|uneb\s+.*answers)",
    r"(write|do)\s+my\s+(homework|assignment|coursework)\s+for\s+me",
    r"(how\s+to\s+)?make\s+(a\s+)?(bomb|weapon|drug|poison)",
    r"(harmful|violent|explicit|sexual)\s+content",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_CONTENT), re.IGNORECASE)


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""


class InputGuard:
    """Check incoming queries for injection attempts and blocked content."""

    def check(self, message: str) -> GuardResult:
        if not message or not message.strip():
            return GuardResult(allowed=False, reason="Please type or speak a question.")

        if len(message) > MAX_INPUT_LENGTH:
            return GuardResult(
                allowed=False,
                reason=f"Message too long (max {MAX_INPUT_LENGTH} characters). Please shorten your question.",
            )

        if _INJECTION_RE.search(message):
            logger.warning("Prompt injection attempt detected")
            return GuardResult(
                allowed=False,
                reason="I can only help with A-Level STEM questions. Please ask a study-related question.",
            )

        if _BLOCKED_RE.search(message):
            logger.warning("Blocked content detected")
            return GuardResult(
                allowed=False,
                reason=(
                    "I'm here to help you learn, not to provide shortcuts. "
                    "Let me help you understand the topic step by step instead."
                ),
            )

        return GuardResult(allowed=True)


class OutputGuard:
    """Post-generation safety checks."""

    def should_abstain(self, hits: list[dict]) -> bool:
        """Return True if retrieval confidence is too low to answer."""
        if not hits:
            return True

        # Keyword fallback hits have no scores — trust them if they exist
        # (they already passed word-overlap filtering)
        has_any_score = any(
            h.get("score_rerank") or h.get("score_rrf")
            for h in hits[:3]
        )
        if not has_any_score:
            # Keyword-only mode: we have hits, so proceed
            return False

        top_scores = [
            h.get("score_rerank", h.get("score_rrf", 0.0))
            for h in hits[:3]
        ]
        avg_score = sum(top_scores) / len(top_scores)
        return avg_score < ABSTENTION_THRESHOLD
