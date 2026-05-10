"""Integration test for run_briefing with a fake LLM and fake FHIR client."""
from __future__ import annotations

from typing import Any

import pytest

import app.tools  # noqa: F401  -- side-effect: registers tools
import app.tools.chw as chw_tools
from app.agents import briefing as briefing_mod
from app.agents.briefing import run_briefing
from app.fhir.id_map import IdMap
from app.llm.client import LLM


# ── Fakes ──────────────────────────────────────────────────────────────


class FakeFhir:
    """Minimal stand-in for FhirClient used by the registered tools."""

    def __init__(self, count_value: int = 5) -> None:
        self.count_value = count_value
        self.count_calls: list[tuple[str, dict[str, Any] | None]] = []

    async def count(self, resource_type: str, params: dict[str, Any] | None = None) -> int:
        self.count_calls.append((resource_type, params))
        return self.count_value


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[_FakeToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.role = "assistant"

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        if exclude_none:
            out = {k: v for k, v in out.items() if v is not None}
        return out


class _FakeChoice:
    def __init__(self, msg: _FakeMessage) -> None:
        self.message = msg


class _FakeCompletion:
    def __init__(self, msg: _FakeMessage) -> None:
        self.choices = [_FakeChoice(msg)]


class FakeLLM:
    """Returns scripted responses on successive `chat()` calls."""

    def __init__(self, scripted: list[_FakeMessage]) -> None:
        self.scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []
        self.model = "fake-model"
        self.provider = "fake"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> _FakeCompletion:
        self.calls.append({"messages": list(messages), "tools": tools})
        msg = self.scripted.pop(0)
        return _FakeCompletion(msg)


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_id_map(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = IdMap(
        patients={"syn-001": "uuid-pat-1"},
        practitioners={f"chw-{i:03d}": f"uuid-chw-{i}" for i in range(1, 4)},
    )
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake)


@pytest.fixture(autouse=True)
def disable_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic — never ship traces during pytest."""
    monkeypatch.setattr(briefing_mod, "get_langfuse", lambda: None)


# ── Test ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_briefing_calls_tool_then_answers() -> None:
    fhir = FakeFhir(count_value=10)

    scripted = [
        # Turn 1: model asks for team_activity_summary.
        _FakeMessage(
            tool_calls=[
                _FakeToolCall(
                    call_id="call_1",
                    name="team_activity_summary",
                    arguments='{"days": 14}',
                )
            ]
        ),
        # Turn 2: model produces the final briefing.
        _FakeMessage(content="All 3 CHWs logged 10 encounters each."),
    ]
    llm = FakeLLM(scripted)

    result = await run_briefing(
        "How is the team doing?",
        fhir=fhir,  # type: ignore[arg-type]
        llm=llm,    # type: ignore[arg-type]
        lookback_days=14,
    )

    assert result.iterations == 2
    assert result.tool_calls == 1
    assert "10 encounters" in result.answer

    # Trace contains both the tool_call and tool_result, then assistant.
    kinds = [t.kind for t in result.trace]
    assert kinds == ["tool_call", "tool_result", "assistant"]
    assert result.trace[0].name == "team_activity_summary"
    assert result.trace[0].arguments == {"days": 14}
    assert result.trace[1].result["stats"]["total"] == 30  # 3 CHWs × 10
    assert result.trace[1].result["days"] == 14

    # The system prompt must have been templated with lookback_days=14.
    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert "Default lookback window: 14 days" in system_prompt

    # FHIR was called once per CHW.
    assert len(fhir.count_calls) == 3
