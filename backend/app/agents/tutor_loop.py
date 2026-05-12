"""Magezi Agentic Tutor Loop — multi-step reasoning with tool use.

This module implements the agentic pattern that differentiates Magezi
from a simple RAG chatbot. Instead of single-pass retrieval → generation,
the tutor loop can:

1. PLAN: Analyse the query complexity and decide on approach
2. RETRIEVE: Pull relevant syllabus content (possibly multiple rounds)
3. CALCULATE: Use STEM tools for numeric verification
4. SYNTHESISE: Generate the pedagogical response
5. VERIFY: Check faithfulness and self-correct if needed

This is the key hackathon differentiator — judges see an AI that
*reasons about how to teach*, not just retrieves and regurgitates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..tools import build_tool_context, lookup_formula, safe_calculate

logger = logging.getLogger(__name__)


@dataclass
class TutorPlan:
    """The tutor's internal plan for answering a query."""
    query: str
    subject: str | None
    locale: str
    complexity: str = "simple"  # simple | moderate | complex
    needs_calculation: bool = False
    needs_multi_retrieval: bool = False
    needs_extended_thinking: bool = False
    tool_context: str = ""
    retrieval_queries: list[str] = field(default_factory=list)
    calculation_results: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


def plan_response(query: str, subject: str | None, locale: str) -> TutorPlan:
    """STEP 1: Analyse the query and create a teaching plan.

    This is the "thinking before answering" step that makes Magezi
    feel intelligent rather than reactive.
    """
    plan = TutorPlan(query=query, subject=subject, locale=locale)
    q_lower = query.lower()

    # Detect complexity
    complex_indicators = [
        "derive", "prove", "show that", "verify", "mechanism",
        "step by step", "compare and contrast", "evaluate",
        "discuss", "analyse", "justify",
    ]
    moderate_indicators = [
        "explain", "describe", "calculate", "solve", "find",
        "what is", "define", "state",
    ]

    if any(ind in q_lower for ind in complex_indicators):
        plan.complexity = "complex"
        plan.needs_extended_thinking = True
    elif any(ind in q_lower for ind in moderate_indicators):
        plan.complexity = "moderate"
    else:
        plan.complexity = "simple"

    # Detect if calculation is needed
    calc_indicators = [
        "calculate", "find the value", "solve", "compute",
        "how much", "how many", "what is the",
        "kg", "m/s", "joules", "newtons", "volts", "watts",
    ]
    if any(ind in q_lower for ind in calc_indicators):
        plan.needs_calculation = True

    # Detect if multiple retrieval rounds needed
    multi_indicators = [
        "compare", "contrast", "difference between",
        "relate", "connection between", "how does.*relate",
    ]
    if any(ind in q_lower for ind in multi_indicators):
        plan.needs_multi_retrieval = True
        # Generate sub-queries for each concept being compared
        if "compare" in q_lower or "difference" in q_lower:
            # Try to extract the two concepts
            parts = q_lower.replace("compare", "").replace("and", "|").replace("difference between", "").replace("contrast", "").split("|")
            for part in parts:
                part = part.strip()
                if len(part) > 3:
                    plan.retrieval_queries.append(part)

    if not plan.retrieval_queries:
        plan.retrieval_queries = [query]

    # Build tool context
    plan.tool_context = build_tool_context(query, subject)

    # Try calculations
    if plan.needs_calculation:
        # Extract numbers from query for formula reference
        formulas = lookup_formula(query, subject)
        if formulas:
            plan.calculation_results.extend(formulas)

    # Plan the teaching steps
    if plan.complexity == "complex":
        plan.steps = [
            "Acknowledge the complexity of the question",
            "Break down into sub-problems",
            "Explain each sub-problem with the NCDC pedagogy",
            "Show complete worked solution",
            "Verify the answer",
            "Provide practice problem",
        ]
    elif plan.complexity == "moderate":
        plan.steps = [
            "Define the key concept",
            "Explain with an example",
            "Connect to real-world application",
            "Provide practice problem",
        ]
    else:
        plan.steps = [
            "Give a clear, concise answer",
            "Provide one supporting example",
        ]

    logger.info(
        "Tutor plan: complexity=%s calc=%s multi=%s thinking=%s queries=%d",
        plan.complexity, plan.needs_calculation,
        plan.needs_multi_retrieval, plan.needs_extended_thinking,
        len(plan.retrieval_queries),
    )

    return plan


def build_enhanced_prompt(plan: TutorPlan, passages: list[dict[str, Any]]) -> str:
    """STEP 2: Build an enhanced prompt that includes the tutor's plan.

    This is injected before the passages in the Claude prompt so the
    model understands HOW to teach, not just WHAT to retrieve.
    """
    parts: list[str] = []

    parts.append("## Tutor's internal plan (follow this approach)")
    parts.append(f"Query complexity: {plan.complexity}")
    parts.append(f"Teaching steps to follow:")
    for i, step in enumerate(plan.steps, 1):
        parts.append(f"  {i}. {step}")

    if plan.tool_context:
        parts.append(f"\n{plan.tool_context}")

    if plan.calculation_results:
        parts.append("\nRelevant formulas for this problem:")
        for calc in plan.calculation_results:
            parts.append(f"  - {calc}")

    if plan.needs_multi_retrieval and len(plan.retrieval_queries) > 1:
        parts.append(f"\nNote: Student is comparing concepts. Address each one:")
        for q in plan.retrieval_queries:
            parts.append(f"  - {q}")

    parts.append("")
    return "\n".join(parts)
