"""The multi-agent graph end to end, with a fake LLM that answers by role."""
from __future__ import annotations

from typing import Any

import pytest

import app.tools  # noqa: F401  -- side-effect: registers tools
import app.tools.chw as chw_tools
from app.agents import briefing as briefing_mod
from app.agents.briefing import StreamEvent, run_briefing
from app.agents.graph import _parse_route
from app.fhir.id_map import IdMap
from tests.integration.test_briefing_agent import (
    FakeFhir,
    _FakeCompletion,
    _FakeMessage,
    _FakeToolCall,
)


class RoleLLM:
    """Replies according to which agent is asking (read off the system prompt).

    Specialists run in parallel, so a strictly ordered script would be racy.
    """

    model = "fake-model"
    provider = "fake"

    def __init__(self, replies: dict[str, list[_FakeMessage]]) -> None:
        self.replies = replies
        self.asked: list[str] = []

    async def chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> _FakeCompletion:
        system = messages[0]["content"]
        role = next(
            r
            for r, marker in {
                "router": "You route",
                "team": "team activity analyst",
                "clinical": "clinical signals analyst",
                "quality": "data quality analyst",
                "lead": "lead analyst",
            }.items()
            if marker in system
        )
        self.asked.append(role)
        return _FakeCompletion(self.replies[role].pop(0))


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = IdMap(
        patients={},
        practitioners={f"chw-{i:03d}": f"uuid-chw-{i}" for i in range(1, 4)},
    )
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake)
    monkeypatch.setattr(briefing_mod, "get_langfuse", lambda: None)


async def _run(llm: RoleLLM) -> tuple[Any, list[StreamEvent]]:
    events: list[StreamEvent] = []

    async def collect(ev: StreamEvent) -> None:
        events.append(ev)

    result = await run_briefing(
        "Give me the Monday briefing.",
        fhir=FakeFhir(count_value=12),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        on_event=collect,
    )
    return result, events


async def test_all_specialists_report_and_ungrounded_figures_are_revised() -> None:
    llm = RoleLLM(
        {
            "router": [
                _FakeMessage(
                    content='{"agents": ["team", "clinical", "quality"], "reason": "x"}'
                )
            ],
            "team": [
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("c1", "team_activity_summary", '{"days": 30}')
                    ]
                ),
                _FakeMessage(content="- chw-001: 12 visits."),
            ],
            "clinical": [_FakeMessage(content="- Nothing notable.")],
            "quality": [_FakeMessage(content="- Nothing notable.")],
            "lead": [
                # First draft invents a CHW and a count no tool returned.
                _FakeMessage(content="- chw-099 logged 777 visits; call them."),
                _FakeMessage(content="- chw-001 logged 12 visits; no action."),
            ],
        }
    )

    result, events = await _run(llm)

    assert result.route == ["team", "clinical", "quality"]
    assert [a.name for a in result.agents] == ["team", "clinical", "quality"]
    assert result.answer == "- chw-001 logged 12 visits; no action."
    assert result.verification == {
        "grounded": True,
        "figures_checked": 1,
        "ungrounded_numbers": [],
        "ungrounded_chw_ids": [],
        "revisions": 1,
    }
    assert [p.agent for p in result.plan] == ["team"]

    verifies = [e.verification for e in events if e.kind == "verify"]
    # "99" is the digits of the invented chw-099, which no tool returned either.
    assert verifies[0]["ungrounded_numbers"] == ["777", "99"]
    assert verifies[0]["ungrounded_chw_ids"] == ["chw-099"]
    assert verifies[1]["grounded"] is True
    assert {e.agent for e in events if e.kind == "agent_done"} == {
        "team",
        "clinical",
        "quality",
    }
    assert llm.asked.count("lead") == 2


async def test_stops_revising_after_one_attempt() -> None:
    llm = RoleLLM(
        {
            "router": [_FakeMessage(content='{"agents": ["team", "quality"]}')],
            "team": [_FakeMessage(content="- Nothing notable.")],
            "quality": [_FakeMessage(content="- Nothing notable.")],
            "lead": [
                _FakeMessage(content="- 777 visits."),
                _FakeMessage(content="- 888 visits."),
            ],
        }
    )

    result, _ = await _run(llm)

    assert result.answer == "- 888 visits."
    assert result.verification["grounded"] is False
    assert result.verification["ungrounded_numbers"] == ["888"]
    assert result.verification["revisions"] == 1


async def test_malformed_tool_arguments_go_back_to_the_model() -> None:
    llm = RoleLLM(
        {
            "router": [_FakeMessage(content='{"agents": ["team"]}')],
            "team": [
                _FakeMessage(
                    tool_calls=[_FakeToolCall("c1", "team_activity_summary", "{days:")]
                ),
                _FakeMessage(content="- Could not read the data."),
            ],
        }
    )

    result, _ = await _run(llm)

    assert "not valid JSON" in result.trace[1].result["error"]
    assert result.answer == "- Could not read the data."


def test_unreadable_route_engages_every_specialist() -> None:
    assert _parse_route("not json")[0] == ["team", "clinical", "quality"]
    assert _parse_route('{"agents": ["nobody"]}')[0] == ["team", "clinical", "quality"]
    assert _parse_route('{"agents": ["quality"], "reason": "r"}') == (["quality"], "r")
