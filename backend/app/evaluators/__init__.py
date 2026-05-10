"""Evaluator scorers for the briefing agent.

Each scorer returns an `EvalScore(name, value in [0, 1], comment)` and is a
pure function over the agent's `BriefingResult` (or its raw fields). They are
intentionally LLM-free so they can run in CI and on every commit without an
API key.

Composite runner: `evaluate_briefing(result)` returns a list of scores.
"""
from app.evaluators.scorers import (
    EvalScore,
    conciseness,
    entity_grounding,
    evaluate_briefing,
    iteration_efficiency,
    numeric_fidelity,
    plan_minimality,
)

__all__ = [
    "EvalScore",
    "conciseness",
    "entity_grounding",
    "evaluate_briefing",
    "iteration_efficiency",
    "numeric_fidelity",
    "plan_minimality",
]
