"""Unit tests for the LLM-as-judge scorers.

These never hit the network — every test injects a `judge_fn` stub.
"""
from __future__ import annotations

import pytest

from app.agents.briefing import BriefingResult, TraceEvent
from app.evaluators import (
    evaluate_briefing_with_judges,
    judge_action_orientation,
    judge_citation_discipline,
)
from app.evaluators.judge import (
    _parse_judge_payload,
    _summarise_trace,
)


def _result(answer: str = "x", trace: list[TraceEvent] | None = None) -> BriefingResult:
    return BriefingResult(answer=answer, trace=trace or [], iterations=1, tool_calls=1)


def _stub(score: float, reason: str = "ok"):
    """Build a judge_fn stub that returns a fixed payload and records inputs."""
    captured: dict = {}

    async def fn(system: str, user: str) -> dict:
        captured["system"] = system
        captured["user"] = user
        return {"score": score, "reason": reason}

    return fn, captured


# ─── _parse_judge_payload ───────────────────────────────────────────────────


def test_parse_payload_happy_path():
    score, reason = _parse_judge_payload('{"score": 0.8, "reason": "good"}')
    assert score == 0.8
    assert reason == "good"


def test_parse_payload_clamps_out_of_range():
    score, _ = _parse_judge_payload('{"score": 1.5, "reason": "x"}')
    assert score == 1.0
    score, _ = _parse_judge_payload('{"score": -0.2, "reason": "x"}')
    assert score == 0.0


def test_parse_payload_non_json():
    score, reason = _parse_judge_payload("not json at all")
    assert score == 0.0
    assert "non-JSON" in reason


def test_parse_payload_non_numeric_score():
    score, reason = _parse_judge_payload('{"score": "high", "reason": "x"}')
    assert score == 0.0
    assert "non-numeric" in reason


def test_parse_payload_missing_reason():
    score, reason = _parse_judge_payload('{"score": 0.5}')
    assert score == 0.5
    assert reason  # placeholder applied


# ─── _summarise_trace ───────────────────────────────────────────────────────


def test_summarise_trace_renders_calls_results_and_assistants():
    trace = [
        TraceEvent(kind="tool_call", name="team_activity_summary",
                   arguments={"days": 30}),
        TraceEvent(kind="tool_result", name="team_activity_summary",
                   result={"rows": [{"chw_id": "chw-002", "encounter_count": 16}]}),
        TraceEvent(kind="assistant", content="Calling another tool to confirm."),
    ]
    out = _summarise_trace(trace)
    assert "CALL team_activity_summary" in out
    assert "RESULT team_activity_summary" in out
    assert "chw-002" in out
    assert "ASSISTANT:" in out


def test_summarise_trace_truncates_huge_results():
    big = {"rows": [{"i": i, "name": "x" * 200} for i in range(500)]}
    trace = [TraceEvent(kind="tool_result", name="t", result=big)]
    out = _summarise_trace(trace)
    assert "(truncated)" in out
    # And the overall budget is respected.
    assert len(out) < 9000


# ─── individual judges ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_orientation_passes_through_score_and_reason():
    fn, captured = _stub(0.9, "names a concrete next step")
    score = await judge_action_orientation(
        _result("Call chw-002 today to check phone."),
        question="anything unusual?",
        judge_fn=fn,
    )
    assert score.name == "judge_action_orientation"
    assert score.value == 0.9
    assert "concrete next step" in score.comment
    # The judge prompt embeds the rubric and the answer.
    assert "ACTION ORIENTATION" in captured["system"]
    assert "Call chw-002 today" in captured["user"]


@pytest.mark.asyncio
async def test_citation_discipline_passes_through():
    fn, _ = _stub(0.4, "vague")
    score = await judge_citation_discipline(
        _result("Several CHWs are slow."),
        question="who is slow?",
        judge_fn=fn,
    )
    assert score.name == "judge_citation_discipline"
    assert score.value == 0.4
    assert score.comment == "vague"


@pytest.mark.asyncio
async def test_judge_clamps_out_of_range_value():
    fn, _ = _stub(2.5, "model overshoot")
    score = await judge_action_orientation(
        _result("a"), question="q", judge_fn=fn
    )
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_judge_handles_callable_exception_gracefully():
    async def boom(_s: str, _u: str) -> dict:
        raise RuntimeError("network down")

    score = await judge_citation_discipline(
        _result("a"), question="q", judge_fn=boom
    )
    assert score.value == 0.0
    assert "network down" in score.comment


# ─── composite ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_briefing_with_judges_runs_both():
    fn, _ = _stub(0.7, "fine")
    scores = await evaluate_briefing_with_judges(
        _result("a"), question="q", judge_fn=fn
    )
    names = {s.name for s in scores}
    assert names == {"judge_action_orientation", "judge_citation_discipline"}
    assert all(s.value == 0.7 for s in scores)
