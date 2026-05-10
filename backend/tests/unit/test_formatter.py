"""Unit tests for the structured-answer formatter — no LLM/network."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.agents.briefing import BriefingResult, PlanStep
from app.agents.formatter import (
    AnswerDoc,
    _fallback_doc,
    _normalise_section,
    _safe_parse,
    format_answer,
)


def _result(answer: str = "", plan: list[PlanStep] | None = None) -> BriefingResult:
    return BriefingResult(
        answer=answer,
        iterations=1,
        tool_calls=len(plan or []),
        plan=plan or [],
    )


# ─── _safe_parse ────────────────────────────────────────────────────────────


def test_safe_parse_returns_dict_for_valid_json():
    assert _safe_parse('{"a": 1}') == {"a": 1}


def test_safe_parse_returns_none_for_garbage():
    assert _safe_parse("not json") is None
    assert _safe_parse("") is None
    assert _safe_parse("[1, 2]") is None  # list, not dict


# ─── _normalise_section ─────────────────────────────────────────────────────


def test_normalise_drops_unknown_kind():
    assert _normalise_section({"kind": "wat"}) is None
    assert _normalise_section("not a dict") is None


def test_normalise_stat_row_clamps_to_four_and_defaults_tone():
    s = _normalise_section({
        "kind": "stat-row",
        "stats": [
            {"label": "A", "value": "1", "delta": "+", "deltaTone": "ok",  "sub": "x"},
            {"label": "B", "value": "2", "delta": "-", "deltaTone": "wat", "sub": "y"},
            {"label": "C", "value": "3"},
            {"label": "D", "value": "4"},
            {"label": "E", "value": "5"},  # 5th — should be dropped.
        ],
    })
    assert s["kind"] == "stat-row"
    assert len(s["stats"]) == 4
    assert s["stats"][1]["deltaTone"] == "muted"  # invalid tone fell back


def test_normalise_callout_validates_tone_and_evidence():
    s = _normalise_section({
        "kind": "callout",
        "tone": "bogus",
        "title": "T",
        "body": "B",
        "evidence": ["chw_inactivity", 1, {"bad": True}, "visits_by_day"],
    })
    assert s["tone"] == "ok"  # invalid tone defaults to ok
    # evidence keeps strings + numerics, drops dicts
    assert s["evidence"] == ["chw_inactivity", "1", "visits_by_day"]


def test_normalise_ranked_drops_items_without_id():
    s = _normalise_section({
        "kind": "ranked",
        "title": "Top",
        "tone": "ok",
        "items": [
            {"id": "chw-009", "primary": "p", "secondary": "s"},
            {"primary": "no id"},
            {"id": "chw-019"},
        ],
    })
    assert [i["id"] for i in s["items"]] == ["chw-009", "chw-019"]


def test_normalise_ranked_returns_none_when_all_items_invalid():
    assert _normalise_section({
        "kind": "ranked",
        "items": [{"primary": "no id"}, "garbage"],
    }) is None


def test_normalise_panel_keeps_well_formed_rows():
    s = _normalise_section({
        "kind": "panel",
        "title": "Panel",
        "rows": [
            {"left": "Mary", "mid": "F · 34", "right": "Apr 18"},
            "garbage",
            {"left": "Joe", "mid": "M · 67", "right": "Apr 16"},
        ],
    })
    assert [r["left"] for r in s["rows"]] == ["Mary", "Joe"]


# ─── _fallback_doc ─────────────────────────────────────────────────────────


def test_fallback_doc_wraps_markdown_as_callout():
    plan = [PlanStep(tool="team_activity_summary", args="(days=30)", ms=120, rows=30)]
    r = _result(answer="Headline line.\nMore detail here.", plan=plan)
    doc = _fallback_doc(r)
    assert doc.headline.startswith("Headline line")
    assert len(doc.sections) == 1
    assert doc.sections[0]["kind"] == "callout"
    assert doc.sections[0]["evidence"] == ["team_activity_summary"]
    assert doc.sources == ["team_activity_summary(days=30)"]


# ─── format_answer (with stub LLM) ─────────────────────────────────────────


@dataclass
class _FakeMsg:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMsg


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


class _FakeLLM:
    """Quacks like LLM.chat — returns a canned JSON string."""

    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCompletion(choices=[_FakeChoice(message=_FakeMsg(content=self.payload))])


@pytest.mark.asyncio
async def test_format_answer_parses_clean_json():
    payload = json.dumps({
        "headline": "Team is on-trend; chw-002 is silent.",
        "period": "Apr 11 → May 10 · 30-day lookback",
        "sections": [
            {"kind": "stat-row", "stats": [
                {"label": "ENCOUNTERS", "value": "3,748", "delta": "+4.2%",
                 "deltaTone": "ok", "sub": "vs prior 30d"},
            ]},
            {"kind": "ranked", "title": "Needs follow-up", "tone": "alert",
             "items": [{"id": "chw-002", "primary": "16 encs",
                        "secondary": "0 in last 7d"}]},
        ],
        "sources": ["team_activity_summary(days=30)"],
    })
    llm = _FakeLLM(payload)
    plan = [PlanStep(tool="team_activity_summary", args="(days=30)", ms=120, rows=30)]
    doc = await format_answer(_result("md", plan), question="q", llm=llm)
    assert isinstance(doc, AnswerDoc)
    assert doc.headline.startswith("Team is on-trend")
    assert doc.period.startswith("Apr 11")
    assert {s["kind"] for s in doc.sections} == {"stat-row", "ranked"}
    assert doc.sources == ["team_activity_summary(days=30)"]
    # The user payload includes the markdown answer + the plan summary.
    assert "team_activity_summary" in llm.calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_format_answer_falls_back_on_garbage():
    llm = _FakeLLM("not json at all")
    plan = [PlanStep(tool="list_chws", args="()", ms=80, rows=30)]
    doc = await format_answer(_result("Some markdown.", plan), question="q", llm=llm)
    # Should produce a non-empty fallback doc, not raise.
    assert doc.sections
    assert doc.sections[0]["kind"] == "callout"
    assert doc.sources == ["list_chws()"]


@pytest.mark.asyncio
async def test_format_answer_falls_back_when_no_renderable_sections():
    # Valid JSON, but every section is invalid → fallback so the UI never
    # ends up with an empty card.
    payload = json.dumps({
        "headline": "h",
        "sections": [{"kind": "ranked", "items": [{"primary": "no id"}]}],
        "sources": ["t()"],
    })
    llm = _FakeLLM(payload)
    plan = [PlanStep(tool="t", args="()", ms=10, rows=0)]
    doc = await format_answer(_result("md", plan), question="q", llm=llm)
    assert doc.sections[0]["kind"] == "callout"  # fallback


@pytest.mark.asyncio
async def test_format_answer_uses_plan_when_sources_missing():
    payload = json.dumps({
        "headline": "h",
        "sections": [{"kind": "callout", "tone": "ok", "title": "t", "body": "b"}],
    })
    llm = _FakeLLM(payload)
    plan = [
        PlanStep(tool="a", args="()", ms=10, rows=1),
        PlanStep(tool="b", args="(x=1)", ms=20, rows=2),
    ]
    doc = await format_answer(_result("md", plan), question="q", llm=llm)
    assert doc.sources == ["a()", "b(x=1)"]


@pytest.mark.asyncio
async def test_format_answer_falls_back_when_llm_raises():
    class _BoomLLM:
        async def chat(self, **_kw):
            raise RuntimeError("provider down")

    plan = [PlanStep(tool="t", args="()", ms=10, rows=0)]
    doc = await format_answer(_result("md", plan), question="q", llm=_BoomLLM())
    # Fallback doc — single callout, never raised.
    assert doc.sections[0]["kind"] == "callout"
