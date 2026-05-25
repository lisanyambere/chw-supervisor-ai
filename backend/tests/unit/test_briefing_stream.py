"""SSE streaming for /briefing/stream — agent event hook + endpoint."""
from __future__ import annotations

import json
from typing import Any

import pytest

import app.tools  # noqa: F401  — side effect: registers tools
import app.tools.chw as chw_tools
from app.agents import briefing as briefing_mod
from app.agents.briefing import StreamEvent, run_briefing
from app.fhir.id_map import IdMap

# Reuse the fake-LLM scaffolding from the integration test by re-importing it.
from tests.integration.test_briefing_agent import (  # noqa: E402
    FakeFhir,
    FakeLLM,
    _FakeMessage,
    _FakeToolCall,
)


@pytest.fixture(autouse=True)
def patch_id_map(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = IdMap(
        patients={"syn-001": "uuid-pat-1"},
        practitioners={f"chw-{i:03d}": f"uuid-chw-{i}" for i in range(1, 4)},
    )
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake)


@pytest.fixture(autouse=True)
def disable_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(briefing_mod, "get_langfuse", lambda: None)


@pytest.mark.asyncio
async def test_on_event_fires_tool_start_done_response_in_order() -> None:
    fhir = FakeFhir(count_value=7)
    scripted = [
        _FakeMessage(
            tool_calls=[
                _FakeToolCall(
                    call_id="call_1",
                    name="team_activity_summary",
                    arguments='{"days": 30}',
                )
            ]
        ),
        _FakeMessage(content="Three CHWs at 7 each."),
    ]
    llm = FakeLLM(scripted)

    events: list[StreamEvent] = []

    async def collector(ev: StreamEvent) -> None:
        events.append(ev)

    await run_briefing(
        "How is the team?",
        fhir=fhir,  # type: ignore[arg-type]
        llm=llm,    # type: ignore[arg-type]
        on_event=collector,
    )

    kinds = [e.kind for e in events]
    assert kinds == ["tool_start", "tool_done", "response"]

    start, done, resp = events
    assert start.tool == "team_activity_summary"
    assert start.args == "(days=30)"

    assert done.tool == "team_activity_summary"
    assert done.args == "(days=30)"
    assert done.ms is not None and done.ms >= 0
    assert done.rows is not None and done.rows >= 1

    assert resp.answer == "Three CHWs at 7 each."
    assert resp.iterations == 2
    assert resp.tool_calls == 1
    assert resp.plan is not None and len(resp.plan) == 1


@pytest.mark.asyncio
async def test_on_event_handles_parallel_tool_calls() -> None:
    # The LLM asks for two tools in one turn — assert two tool_starts
    # then two tool_dones (each in some order), then response.
    fhir = FakeFhir(count_value=4)
    scripted = [
        _FakeMessage(
            tool_calls=[
                _FakeToolCall("c1", "team_activity_summary", '{"days": 7}'),
                _FakeToolCall("c2", "list_chws", "{}"),
            ]
        ),
        _FakeMessage(content="ok"),
    ]
    llm = FakeLLM(scripted)

    events: list[StreamEvent] = []

    async def collector(ev: StreamEvent) -> None:
        events.append(ev)

    await run_briefing(
        "stats?",
        fhir=fhir,  # type: ignore[arg-type]
        llm=llm,    # type: ignore[arg-type]
        on_event=collector,
    )

    starts = [e for e in events if e.kind == "tool_start"]
    dones = [e for e in events if e.kind == "tool_done"]
    final = [e for e in events if e.kind == "response"]

    assert {s.tool for s in starts} == {"team_activity_summary", "list_chws"}
    assert {d.tool for d in dones} == {"team_activity_summary", "list_chws"}
    assert len(final) == 1

    # tool_start events fire BEFORE any tool_done — preserves the
    # "agent decided to call all of these" semantics on the wire.
    first_done_idx = next(
        i for i, e in enumerate(events) if e.kind == "tool_done"
    )
    last_start_idx = max(
        i for i, e in enumerate(events) if e.kind == "tool_start"
    )
    assert last_start_idx < first_done_idx


@pytest.mark.asyncio
async def test_to_dict_strips_none_fields() -> None:
    ev = StreamEvent(kind="tool_start", tool="x", args="()")
    assert ev.to_dict() == {"kind": "tool_start", "tool": "x", "args": "()"}


def test_sse_endpoint_streams_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: the SSE endpoint serialises StreamEvents as SSE frames."""
    from fastapi.testclient import TestClient

    from app.api.main import app, get_fhir

    fhir = FakeFhir(count_value=2)
    scripted = [
        _FakeMessage(
            tool_calls=[
                _FakeToolCall("c1", "team_activity_summary", '{"days": 14}')
            ]
        ),
        _FakeMessage(content="done"),
    ]
    llm = FakeLLM(scripted)

    # Stub the LLM factory and the FHIR DI in one shot.
    from app.agents import briefing as briefing_mod_inner
    from app.llm import client as llm_client_mod

    monkeypatch.setattr(briefing_mod_inner, "get_llm", lambda: llm)
    monkeypatch.setattr(llm_client_mod, "get_llm", lambda: llm)
    monkeypatch.setattr(briefing_mod_inner, "get_langfuse", lambda: None)

    fake_idmap = IdMap(
        patients={"syn-001": "uuid-pat-1"},
        practitioners={f"chw-{i:03d}": f"uuid-chw-{i}" for i in range(1, 4)},
    )
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake_idmap)

    app.dependency_overrides[get_fhir] = lambda: fhir
    try:
        with TestClient(app) as client, client.stream(
            "GET",
            "/briefing/stream",
            params={"question": "hi", "lookback_days": 14},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith(
                "text/event-stream"
            )

            events: list[dict[str, Any]] = []
            current_event: str | None = None
            for raw in response.iter_lines():
                line = raw if isinstance(raw, str) else raw.decode()
                if line.startswith("event: "):
                    current_event = line[len("event: ") :]
                elif line.startswith("data: "):
                    events.append(
                        {
                            "kind": current_event,
                            "payload": json.loads(line[len("data: ") :]),
                        }
                    )
    finally:
        app.dependency_overrides.pop(get_fhir, None)

    kinds = [e["kind"] for e in events]
    assert kinds == ["tool_start", "tool_done", "response"]
    assert events[-1]["payload"]["answer"] == "done"
