"""LLM-as-judge scorers for the briefing agent.

These complement the deterministic scorers in `scorers.py` by grading qualities
that require natural-language understanding: does the answer recommend a
concrete next action, does every claim cite the evidence behind it.

Design notes
------------
- Each judge calls the configured LLM with `response_format={"type": "json_object"}`
  and parses a strict `{"score": float, "reason": str}` payload. We clamp
  defensively so a misbehaving model can't push values outside [0, 1].
- Judges are *async* and require an `LLM`. Tests inject a fake via the
  `judge_fn` parameter so we never hit the network in unit tests.
- The composite `evaluate_briefing_with_judges` runs both judges in parallel
  via `asyncio.gather` so total latency ≈ one LLM call.
- We deliberately keep the judges pinned to the same model family the agent
  uses; if you want a stronger judge model, override `LLM_PROVIDER`/deployment
  for the eval run.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.core import get_logger
from app.evaluators.scorers import EvalScore
from app.llm import LLM, get_llm

if TYPE_CHECKING:
    from app.agents.briefing import BriefingResult, TraceEvent

log = get_logger(__name__)

# Type for an injectable judge function — used by unit tests to swap the LLM
# call for a deterministic stub.
JudgeFn = Callable[[str, str], Awaitable[dict[str, Any]]]


# ─── prompts ────────────────────────────────────────────────────────────────

_JUDGE_SYSTEM = (
    "You are a strict evaluator grading a community-health-worker (CHW) "
    "supervisor briefing produced by an AI agent. You will be given the "
    "supervisor's question, a compact dump of the tool calls and results "
    "the agent used, and the agent's final answer.\n\n"
    "You always reply with a single JSON object of the form:\n"
    '  {{"score": <float 0..1>, "reason": "<one short sentence>"}}\n\n'
    "Be calibrated. 1.0 means the answer fully meets the criterion; 0.0 "
    "means it clearly fails. Use the middle of the range when partial."
)

_ACTION_RUBRIC = (
    "Criterion: ACTION ORIENTATION. The answer must name at least one "
    "concrete next step a supervisor could take *today* — e.g. \"call "
    "chw-002 to confirm whether their phone is offline\", \"check chw-009's "
    "panel for missed ANC visits\". Generic advice (\"investigate further\", "
    "\"review the data\") does NOT qualify. If the question is purely a "
    "lookup (\"how many CHWs?\") and the answer is a correct one-liner, "
    "score 1.0 — no action is needed. Otherwise reward specificity."
)

_CITATION_RUBRIC = (
    "Criterion: CITATION DISCIPLINE. Every quantitative or named claim in "
    "the answer must be traceable to the tool results shown. Penalise "
    "fabricated numbers, invented CHW ids, vague hedges (\"several CHWs\", "
    "\"recently\") when a precise number was available, and claims about "
    "entities the tools never returned. Reward answers that pin numbers to "
    "the entity they describe (\"chw-002: 16 encounters\") rather than "
    "free-floating stats."
)


# ─── helpers ────────────────────────────────────────────────────────────────


def _summarise_trace(trace: list["TraceEvent"], *, max_chars: int = 8000) -> str:
    """Render the tool-call/result trace as a compact text block for the judge.

    We trim each individual tool result to a budget so a single big list
    doesn't crowd out the rest of the trace. Total output is hard-capped
    at `max_chars` to stay within prompt budgets. The per-result budget is
    intentionally generous (≈2.5kB) so list-style results like `list_chws`
    survive whole — otherwise the judge falsely flags grounded claims as
    untraceable.
    """
    lines: list[str] = []
    for ev in trace:
        if ev.kind == "tool_call":
            args = ev.arguments or {}
            lines.append(f"CALL {ev.name}({json.dumps(args, default=str)})")
        elif ev.kind == "tool_result":
            try:
                payload = json.dumps(ev.result, default=str)
            except (TypeError, ValueError):
                payload = repr(ev.result)
            if len(payload) > 2500:
                payload = payload[:2500] + "…(truncated)"
            lines.append(f"RESULT {ev.name}: {payload}")
        elif ev.kind == "assistant":
            content = (ev.content or "").strip()
            if content:
                lines.append(f"ASSISTANT: {content[:300]}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 14] + "\n…(truncated)"
    return text


def _parse_judge_payload(raw: str) -> tuple[float, str]:
    """Extract `(score, reason)` from a judge response, defensively."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return 0.0, f"judge returned non-JSON: {raw[:120]!r}"
    score = data.get("score")
    reason = str(data.get("reason", "")).strip()
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return 0.0, f"judge returned non-numeric score: {score!r}"
    score_f = max(0.0, min(1.0, score_f))
    if not reason:
        reason = "(no reason given)"
    return score_f, reason


async def _default_judge_fn(system: str, user: str) -> dict[str, Any]:
    """Real LLM call used in production paths."""
    llm = get_llm()
    return await _judge_with_llm(llm, system, user)


async def _judge_with_llm(llm: LLM, system: str, user: str) -> dict[str, Any]:
    """Execute a JSON-mode chat completion and return the parsed payload."""
    resp = await llm.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Force JSON so we don't have to tolerate prose with embedded objects.
        response_format={"type": "json_object"},
        # Judges should be deterministic-ish; we'd set temperature=0 here but
        # GPT-5 family on Azure rejects custom temperatures. The provider
        # default (None on Azure) is fine.
    )
    content = (resp.choices[0].message.content or "").strip()
    score, reason = _parse_judge_payload(content)
    return {"score": score, "reason": reason}


# ─── scorers ────────────────────────────────────────────────────────────────


async def judge_action_orientation(
    result: "BriefingResult",
    question: str,
    *,
    judge_fn: JudgeFn | None = None,
) -> EvalScore:
    """How concrete is the recommended next step?"""
    judge_fn = judge_fn or _default_judge_fn
    system = f"{_JUDGE_SYSTEM}\n\n{_ACTION_RUBRIC}"
    user = (
        f"QUESTION:\n{question}\n\n"
        f"TRACE:\n{_summarise_trace(result.trace)}\n\n"
        f"ANSWER:\n{result.answer}"
    )
    try:
        payload = await judge_fn(system, user)
    except Exception as e:  # noqa: BLE001
        log.warning("judge.action_orientation.failed", error=str(e))
        return EvalScore(
            "judge_action_orientation", 0.0, comment=f"judge call failed: {e}"
        )
    return EvalScore(
        "judge_action_orientation",
        float(payload.get("score", 0.0)),
        comment=str(payload.get("reason", "")),
    )


async def judge_citation_discipline(
    result: "BriefingResult",
    question: str,
    *,
    judge_fn: JudgeFn | None = None,
) -> EvalScore:
    """Are the answer's claims grounded in the trace?"""
    judge_fn = judge_fn or _default_judge_fn
    system = f"{_JUDGE_SYSTEM}\n\n{_CITATION_RUBRIC}"
    user = (
        f"QUESTION:\n{question}\n\n"
        f"TRACE:\n{_summarise_trace(result.trace)}\n\n"
        f"ANSWER:\n{result.answer}"
    )
    try:
        payload = await judge_fn(system, user)
    except Exception as e:  # noqa: BLE001
        log.warning("judge.citation_discipline.failed", error=str(e))
        return EvalScore(
            "judge_citation_discipline", 0.0, comment=f"judge call failed: {e}"
        )
    return EvalScore(
        "judge_citation_discipline",
        float(payload.get("score", 0.0)),
        comment=str(payload.get("reason", "")),
    )


async def evaluate_briefing_with_judges(
    result: "BriefingResult",
    question: str,
    *,
    judge_fn: JudgeFn | None = None,
) -> list[EvalScore]:
    """Run all LLM judges in parallel."""
    return list(
        await asyncio.gather(
            judge_action_orientation(result, question, judge_fn=judge_fn),
            judge_citation_discipline(result, question, judge_fn=judge_fn),
        )
    )


__all__ = [
    "JudgeFn",
    "evaluate_briefing_with_judges",
    "judge_action_orientation",
    "judge_citation_discipline",
]
