"""Unit tests for the evaluator scorers — pure-function, no FHIR/LLM."""
from __future__ import annotations

from app.agents.briefing import BriefingResult, TraceEvent
from app.evaluators import (
    conciseness,
    entity_grounding,
    evaluate_briefing,
    iteration_efficiency,
    numeric_fidelity,
    plan_minimality,
)


def _trace_with(tool_results: list[dict], tool_calls: list[tuple[str, dict]] | None = None):
    events: list[TraceEvent] = []
    calls = tool_calls or [("team_activity_summary", {"days": 30})]
    for name, args in calls:
        events.append(TraceEvent(kind="tool_call", name=name, arguments=args))
    for r in tool_results:
        events.append(TraceEvent(kind="tool_result", name="t", result=r))
    return events


# ─── numeric_fidelity ───────────────────────────────────────────────────────


def test_numeric_fidelity_grounded():
    answer = "chw-009 logged 140 encounters; mean was 124.57."
    trace = _trace_with([
        {"rows": [{"chw_id": "chw-009", "encounter_count": 140}],
         "stats": {"mean": 124.57}},
    ])
    s = numeric_fidelity(answer, trace)
    assert s.value == 1.0


def test_numeric_fidelity_fabricated():
    answer = "chw-009 logged 999 encounters."  # 999 not present
    trace = _trace_with([
        {"rows": [{"chw_id": "chw-009", "encounter_count": 140}]},
    ])
    s = numeric_fidelity(answer, trace)
    assert s.value == 0.0
    assert "999" in s.comment


def test_numeric_fidelity_ignores_allowlisted_small_ints():
    answer = "Top 2 CHWs over the last 30 days."  # 2 and 30 are allowlisted
    s = numeric_fidelity(answer, _trace_with([{"x": 1}]))
    assert s.value == 1.0
    assert "no non-trivial numbers" in s.comment


# ─── entity_grounding ───────────────────────────────────────────────────────


def test_entity_grounding_all_grounded():
    answer = "Top: chw-009. Bottom: chw-002."
    trace = _trace_with([
        {"rows": [{"chw_id": "chw-009"}, {"chw_id": "chw-002"}]},
    ])
    assert entity_grounding(answer, trace).value == 1.0


def test_entity_grounding_partial():
    answer = "Top: chw-009. Bottom: chw-999."  # chw-999 fabricated
    trace = _trace_with([
        {"rows": [{"chw_id": "chw-009"}]},
    ])
    s = entity_grounding(answer, trace)
    assert s.value == 0.5
    assert "chw-999" in s.comment


def test_entity_grounding_no_ids_cited_is_neutral():
    s = entity_grounding("All CHWs are within range.", _trace_with([{"x": 1}]))
    assert s.value == 1.0


# ─── plan_minimality ────────────────────────────────────────────────────────


def test_plan_minimality_one_call_is_perfect():
    s = plan_minimality(_trace_with([{}], tool_calls=[("t", {"a": 1})]))
    assert s.value == 1.0


def test_plan_minimality_too_many_calls_decays():
    calls = [("count_chw_encounters", {"chw_id": f"chw-{i:03d}", "days": 30})
             for i in range(6)]
    s = plan_minimality(_trace_with([{}], tool_calls=calls), expected_max=2)
    assert s.value < 0.5


def test_plan_minimality_duplicate_call_penalised():
    calls = [
        ("team_activity_summary", {"days": 30}),
        ("team_activity_summary", {"days": 30}),  # exact duplicate
    ]
    s = plan_minimality(_trace_with([{}], tool_calls=calls), expected_max=2)
    assert s.value < 1.0
    assert "duplicate" in s.comment


def test_plan_minimality_zero_calls_fails():
    s = plan_minimality([])
    assert s.value == 0.0


# ─── conciseness ────────────────────────────────────────────────────────────


def test_conciseness_in_range():
    answer = "\n".join(f"- bullet {i}" for i in range(5))
    assert conciseness(answer).value == 1.0


def test_conciseness_too_long_decays():
    answer = "\n".join(f"- bullet {i}" for i in range(16))
    s = conciseness(answer)
    assert s.value == 0.0


def test_conciseness_no_bullets_short_prose_ok():
    # Short factual answers shouldn't be penalised for being prose.
    assert conciseness("chw-002 logged 16 encounters.").value == 1.0


def test_conciseness_no_bullets_long_prose_fails():
    long = "Just a paragraph with no structure. " * 20
    assert conciseness(long).value == 0.0


# ─── iteration_efficiency ───────────────────────────────────────────────────


def test_iteration_efficiency_one_iter():
    assert iteration_efficiency(1).value == 1.0


def test_iteration_efficiency_cap_hit():
    assert iteration_efficiency(6, max_iterations=6).value == 0.0


def test_iteration_efficiency_midway():
    s = iteration_efficiency(3, max_iterations=6)
    assert 0.5 < s.value < 0.7


# ─── composite ──────────────────────────────────────────────────────────────


def test_evaluate_briefing_returns_all_scorers():
    result = BriefingResult(
        answer="- chw-009: 140 encounters\n- chw-002: 16 encounters",
        trace=_trace_with(
            [{"rows": [{"chw_id": "chw-009", "encounter_count": 140},
                       {"chw_id": "chw-002", "encounter_count": 16}]}],
            tool_calls=[("team_activity_summary", {"days": 30})],
        ),
        iterations=2,
        tool_calls=1,
    )
    scores = evaluate_briefing(result)
    names = {s.name for s in scores}
    assert names == {
        "numeric_fidelity",
        "entity_grounding",
        "plan_minimality",
        "conciseness",
        "iteration_efficiency",
    }
    by_name = {s.name: s.value for s in scores}
    assert by_name["numeric_fidelity"] == 1.0
    assert by_name["entity_grounding"] == 1.0
    assert by_name["plan_minimality"] == 1.0
