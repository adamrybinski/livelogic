"""LiveLogic Reasoner - DSPy neuro-symbolic pipeline."""

from __future__ import annotations

import logging
from typing import Any

import dspy

logger = logging.getLogger(__name__)

ALLOWED_PREDICATES = {
    "user",
    "resource",
    "action",
    "ip",
    "role",
    "assigned_role",
    "allowed_role",
    "access_event",
    "policy_rule",
    "forbidden_subnet",
    "ip_in_subnet",
    "suggested_role",
}


class ExtractSecurityFacts(dspy.Signature):
    """Extract ASP facts from a natural-language security transcript.

    Only use the whitelisted predicates. Every fact must end with a period.
    """

    transcript: str = dspy.InputField(desc="Spoken or typed user input")
    facts: str = dspy.OutputField(
        desc="ASP facts, one per line, each ending with a period"
    )
    confidence: float = dspy.OutputField(
        desc="Confidence score 0.0-1.0 of extraction accuracy"
    )


class CritiqueUnsat(dspy.Signature):
    """Explain why a set of ASP facts is unsatisfiable and suggest a retraction."""

    unsat_core: str = dspy.InputField(desc="Clingo unsatisfiable core atoms")
    current_facts: str = dspy.InputField(desc="All accumulated facts for this session")
    explanation: str = dspy.OutputField(
        desc="Human-readable explanation of the logical conflict"
    )
    suggested_retraction: str = dspy.OutputField(
        desc="Single fact to retract to restore satisfiability, or empty"
    )


class InterpretAnswer(dspy.Signature):
    """Translate Clingo answer sets into natural language with step-by-step reasoning."""

    answer_sets: str = dspy.InputField(desc="Clingo models as ASP atoms")
    query_context: str = dspy.InputField(desc="Original user question or transcript")
    response: str = dspy.OutputField(
        desc="Natural language response explaining the conclusion"
    )
    reasoning_steps: str = dspy.OutputField(
        desc="Step-by-step logical reasoning trace"
    )


def validate_asp_syntax(facts: str) -> tuple[bool, str]:
    """Return (valid, error_message) after basic syntactic checks."""
    lines = [l.strip() for l in facts.strip().splitlines() if l.strip()]
    for line in lines:
        if not line.endswith("."):
            return False, f"Fact does not end with period: {line}"
        if "(" in line and line.count("(") != line.count(")"):
            return False, f"Unbalanced parentheses: {line}"
        predicate = line.split("(")[0] if "(" in line else line.rstrip(".")
        if predicate not in ALLOWED_PREDICATES:
            return False, f"Unknown predicate: {predicate}"
    return True, ""


def extract_facts_with_confidence(
    transcript: str,
    dspy_module: dspy.Module | None = None,
) -> tuple[str, float]:
    """Run the ExtractSecurityFacts signature and validate output."""
    if dspy_module is None:
        dspy_module = dspy.Predict(ExtractSecurityFacts)

    result = dspy_module(transcript=transcript)
    facts = getattr(result, "facts", "")
    confidence = float(getattr(result, "confidence", 0.0))

    valid, err = validate_asp_syntax(facts)
    if not valid:
        logger.warning("ASP validation failed: %s", err)
        confidence *= 0.5

    return facts, confidence
