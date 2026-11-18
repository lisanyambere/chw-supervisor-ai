"""The briefing team as a LangGraph state graph.

    START → router ─┬→ team ─────┐
                    ├→ clinical ─┼→ synthesize → verify ─→ END
                    └→ quality ──┘        ↑         │
                                          └─ revise ┘  (at most once)

- **router** reads the question and engages only the specialists it needs.
- **specialists** run in parallel, each a tool-calling loop over its own tools.
- **synthesize** merges their findings into one briefing, most urgent first.
- **verify** is deterministic: every number and CHW id in the briefing must
  appear in a tool result. Anything ungrounded goes back for one revision.
"""
from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.briefing import (
    AgentRun,
    BriefingResult,
    OnEvent,
    StreamEvent,
    TraceEvent,
    run_tool_agent,
    traced_chat,
)
from app.core import get_logger
from app.evaluators.scorers import (
    cited_numbers,
    ungrounded_chw_ids,
    ungrounded_numbers,
)
from app.fhir import FhirClient
from app.llm import LLM

log = get_logger(__name__)

MAX_REVISIONS = 1

_SHARED_RULES = """\
Rules:
- Gather data with your tools before concluding anything. Never guess a number.
- Default look-back window: {lookback_days} days. Pass `days={lookback_days}` to
  tools that take `days` unless the supervisor names a different range.
- Report findings as short bullets with exact counts, CHW ids (chw-NNN), ward
  names, patient names and dates copied from the tool results.
- Only report what is notable for a supervisor. If nothing is, say so in one line.
- You are one analyst on a team; stay within your remit and do not write the
  final briefing.
"""

SPECIALISTS: dict[str, dict[str, Any]] = {
    "team": {
        "label": "Team activity",
        "remit": "how active each Community Health Worker (CHW) has been",
        "tools": [
            "list_chws",
            "team_activity_summary",
            "count_chw_encounters",
            "chw_inactivity",
            "chw_activity_gaps",
            "visits_by_day",
            "chw_patient_panel",
        ],
        "guidance": """\
- For a general briefing call both `team_activity_summary` and
  `chw_activity_gaps`.
- A CHW who "stopped_early" has gone quiet: give their last active date and how
  many working days they missed. Their 30-day total can still look normal.
- A CHW who "started_late" has a short history (new or newly registered). A low
  total for them is not low effort; say so instead of ranking them last.
- Judge everyone against the team's first and last active dates, not today's
  date: the whole team may have no data for the most recent days.
""",
    },
    "clinical": {
        "label": "Clinical signals",
        "remit": "patients and households that need attention",
        "tools": [
            "fever_cases_by_ward",
            "child_danger_signs",
            "overdue_followups",
            "recent_deaths",
            "find_patient",
            "get_patient_summary",
        ],
        "guidance": """\
- For a general briefing check all three: `fever_cases_by_ward`,
  `child_danger_signs` and `overdue_followups`.
- Several fever cases in one ward within a few days is a possible outbreak:
  give the ward, the case count, the dates and the CHW who saw them.
- Name each patient who needs action and say why.
""",
    },
    "quality": {
        "label": "Data quality",
        "remit": "records that cannot be right as written",
        "tools": ["visits_missing_location", "visits_after_death"],
        "guidance": """\
- For a general briefing check both tools.
- Say which CHWs the problem records belong to, so the supervisor knows whom
  to ask, and which week the records fall in.
""",
    },
}

_ROUTER_PROMPT = """\
You route a community health supervisor's question to a team of analysts.

Analysts:
- "team": {team}
- "clinical": {clinical}
- "quality": {quality}

Reply with one JSON object: {{"agents": [...], "reason": "<one short sentence>"}}.
Engage every analyst the question needs and no others. A general briefing, or
any open question such as "anything unusual?", needs all three.
"""

_SYNTH_PROMPT = """\
You are the lead analyst writing the briefing a community health program
supervisor in Kakamega, Kenya reads on Monday morning. Your analysts have
reported their findings below.

Write the answer to the supervisor's question:
- 4–8 short bullets for a briefing; one or two lines for a simple lookup.
- Cover every notable finding the analysts report. When there are more
  findings than bullets, combine related ones in a bullet; never drop one.
- Order by urgency: patients at risk first, then team activity, then data quality.
- Each bullet names who or what (CHW id, ward, patient) with the exact figures,
  and ends with the concrete next step for the supervisor.
- Use only numbers, ids and names that appear in the analysts' findings. Do not
  compute new figures.
- Do not mention the analysts or the tools.
"""


class BriefingState(TypedDict, total=False):
    question: str
    route: list[str]
    route_reason: str
    # Parallel specialists each append their run.
    runs: Annotated[list[AgentRun], operator.add]
    llm_calls: Annotated[int, operator.add]
    answer: str
    revisions: int
    verification: dict[str, Any]


def _specialist_prompt(name: str, lookback_days: int) -> str:
    spec = SPECIALISTS[name]
    return str(
        f"You are the {spec['label'].lower()} analyst for a community health "
        f"program supervisor in Kakamega, Kenya. Your remit: {spec['remit']}.\n\n"
        + _SHARED_RULES.format(lookback_days=lookback_days)
        + "\nHow to work:\n"
        + spec["guidance"]
    )


def _tool_trace(runs: list[AgentRun]) -> list[TraceEvent]:
    return [e for run in runs for e in run.trace if e.kind != "assistant"]


def check_grounding(answer: str, runs: list[AgentRun]) -> dict[str, Any]:
    """Deterministic check that the answer cites only what the tools returned."""
    trace = _tool_trace(runs)
    numbers = ungrounded_numbers(answer, trace)
    chw_ids = ungrounded_chw_ids(answer, trace)
    return {
        "grounded": not numbers and not chw_ids,
        "figures_checked": len(cited_numbers(answer)),
        "ungrounded_numbers": numbers,
        "ungrounded_chw_ids": chw_ids,
    }


async def run_graph(
    *,
    question: str,
    fhir: FhirClient,
    llm: LLM,
    max_iterations: int,
    lookback_days: int,
    lf: Any | None,
    on_event: OnEvent | None,
) -> BriefingResult:
    async def emit(event: StreamEvent) -> None:
        if on_event is not None:
            await on_event(event)

    async def router(state: BriefingState) -> BriefingState:
        completion = await traced_chat(
            llm,
            lf,
            "llm.router",
            [
                {
                    "role": "system",
                    "content": _ROUTER_PROMPT.format(
                        **{n: s["remit"] for n, s in SPECIALISTS.items()}
                    ),
                },
                {"role": "user", "content": state["question"]},
            ],
            response_format={"type": "json_object"},
        )
        route, reason = _parse_route(completion.choices[0].message.content)
        await emit(StreamEvent(kind="route", agents=route, reason=reason))
        return {"route": route, "route_reason": reason, "llm_calls": 1}

    def specialist(name: str) -> Any:
        async def node(state: BriefingState) -> BriefingState:
            await emit(StreamEvent(kind="agent_start", agent=name))
            span = (
                lf.start_as_current_observation(name=f"agent.{name}", as_type="agent")
                if lf is not None
                else _NoSpan()
            )
            with span:
                run = await run_tool_agent(
                    name=name,
                    system_prompt=_specialist_prompt(name, lookback_days),
                    tool_names=SPECIALISTS[name]["tools"],
                    question=state["question"],
                    fhir=fhir,
                    llm=llm,
                    max_iterations=max_iterations,
                    lf=lf,
                    on_event=on_event,
                )
            await emit(StreamEvent(kind="agent_done", agent=name, ms=run.ms))
            return {"runs": [run], "llm_calls": run.iterations}

        return node

    async def synthesize(state: BriefingState) -> BriefingState:
        runs = state["runs"]
        verification = state.get("verification")
        if len(runs) == 1 and verification is None:
            # One specialist already answered the question; nothing to merge.
            return {"answer": runs[0].findings}

        findings = "\n\n".join(
            f"## {SPECIALISTS[r.name]['label']} analyst\n{r.findings}" for r in runs
        )
        messages: list[Any] = [
            {"role": "system", "content": _SYNTH_PROMPT},
            {
                "role": "user",
                "content": f"Question: {state['question']}\n\n{findings}",
            },
        ]
        if verification is not None:
            messages += [
                {"role": "assistant", "content": state["answer"]},
                {"role": "user", "content": _revision_request(verification)},
            ]
        completion = await traced_chat(
            llm,
            lf,
            "llm.synthesize" if verification is None else "llm.revise",
            messages,
        )
        return {
            "answer": completion.choices[0].message.content or "",
            "llm_calls": 1,
            "revisions": state.get("revisions", 0) + (verification is not None),
        }

    async def verify(state: BriefingState) -> BriefingState:
        verification = {
            **check_grounding(state["answer"], state["runs"]),
            "revisions": state.get("revisions", 0),
        }
        await emit(StreamEvent(kind="verify", verification=verification))
        return {"verification": verification}

    def after_verify(state: BriefingState) -> str:
        v = state["verification"]
        if not v["grounded"] and v["revisions"] < MAX_REVISIONS:
            return "synthesize"
        return str(END)

    graph = StateGraph(BriefingState)
    graph.add_node("router", router)
    for name in SPECIALISTS:
        graph.add_node(name, specialist(name))
        graph.add_edge(name, "synthesize")
    graph.add_node("synthesize", synthesize)
    graph.add_node("verify", verify)
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", lambda s: s["route"], list(SPECIALISTS))
    graph.add_edge("synthesize", "verify")
    graph.add_conditional_edges("verify", after_verify, ["synthesize", END])

    final = await graph.compile().ainvoke({"question": question})

    # Keep the specialists in a stable order however the parallel step finished.
    runs = sorted(final["runs"], key=lambda r: list(SPECIALISTS).index(r.name))
    return BriefingResult(
        answer=final["answer"],
        trace=[
            *_tool_trace(runs),
            TraceEvent(kind="assistant", content=final["answer"]),
        ],
        iterations=final["llm_calls"],
        tool_calls=sum(r.tool_calls for r in runs),
        route=final["route"],
        route_reason=final["route_reason"],
        agents=runs,
        verification=final["verification"],
    )


def _parse_route(raw: str | None) -> tuple[list[str], str]:
    """Specialists to engage. An unreadable reply engages all of them: the
    cost is a slower answer, where dropping one could hide a finding."""
    try:
        data = json.loads(raw or "")
        route = [a for a in SPECIALISTS if a in data["agents"]]
        reason = str(data.get("reason", ""))
    except (ValueError, TypeError, KeyError):
        log.warning("router.unreadable", raw=(raw or "")[:200])
        return list(SPECIALISTS), "router reply was unreadable; engaged everyone"
    if not route:
        log.warning("router.empty", raw=(raw or "")[:200])
        return list(SPECIALISTS), "router named no analyst; engaged everyone"
    return route, reason


def _revision_request(verification: dict[str, Any]) -> str:
    problems = []
    if verification["ungrounded_numbers"]:
        problems.append(f"numbers {verification['ungrounded_numbers']}")
    if verification["ungrounded_chw_ids"]:
        problems.append(f"CHW ids {verification['ungrounded_chw_ids']}")
    return (
        "A check found figures in your briefing that are not in any analyst's "
        f"data: {' and '.join(problems)}. Rewrite the briefing using only "
        "figures from the findings: correct each one or remove the claim."
    )


class _NoSpan:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None
